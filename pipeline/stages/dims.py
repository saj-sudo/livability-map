"""``dims`` stage (SPEC §5, §20.2, §20.3): attach every non-hazard dimension to the hexes.

For each dimension in ``dimensions.yaml`` the joiners run in registry order and the first one
that yields a value for a hex wins; that joiner's ``res`` tag, source id, scoring ``domain`` and
``label`` travel with the value. Output ``data/interim/dims_r{res}.parquet`` with, per dimension:

- kind ``score``:        ``{id}_raw`` (float32), ``{id}_res``, ``{id}_src``, ``{id}_dom``, ``{id}_lbl``
- kind ``signed``:       ``{id}_lean`` (Int16, rounded and clipped to -100..100), plus the same tags
- kind ``composition``:  ``{id}_w/_b/_h/_a/_o`` (Int8 percents that sum to 100), ``{id}_maj``,
                         plus the same tags

Missing is NaN / ``none``, never 0 (invariant 3). ``_src``, ``_dom`` and ``_lbl`` stay in the
parquet for the manifest and the score stage; only ``_res`` ships in tiles (§6.1).

A joiner whose real source is not downloaded yet is skipped with the source's recipe printed,
so the fallbacks (for example WHR when SHDI is missing) still run and the sanity output shows
the gap honestly.

Each dimension carries its own fingerprint (its sources' raw files, its registry entry, the
hexes / pop / admin of the resolution and the stage code), so a plain run recomputes only the
dimensions whose fingerprint moved and merges them into the existing parquet. That is how a new
layer is added at res 5 without redoing the hour-long US tract overlays. ``run(settings,
only=[...])`` forces the named dimensions; it never marks the others fresh, so a later plain run
still catches a dimension that went stale meanwhile.

Memory (SPEC §13.44): prepared layers load when a dimension first needs them and are dropped
after the last dimension that uses them, and an overlay chunk sees only the polygons near it, so
the peak is the largest dimension's layers, not every layer at once. A layer whose joiner field
is mostly empty stops the run (``min_nonnull``) instead of silently scoring nothing.

Crash resume (SPEC §13.44): each finished dimension is also written as a checkpoint shard under
``dims_r{res}.parts/`` with the same fingerprint the dimension would have in the final file. A run
that dies hours in leaves them, and the next run adopts every shard whose fingerprint still
matches and computes only the rest; the shards are deleted once ``dims_r{res}.parquet`` is written.
"""

from __future__ import annotations

import gc
import hashlib
import shutil
import time
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .. import h3util, prep, stage_cache
from ..config import BBox, Settings
from ..joiners import JOINERS
from ..registry import COMPOSITION_KEYS, Dimension, JoinSpec, Source, load_dimensions, load_sources

OVERLAY_CHUNK = 2000  # hexes per area_weighted_overlay call
MIN_NONNULL = 0.10  # a joiner field must be filled in at least this share of its layer's rows


@dataclass(frozen=True)
class RasterLayer:
    """A raster source as the dims stage sees it: the GeoTIFF to read and its nodata sentinel
    (from `nodata:` on the source; the file's own nodata tag is the fallback)."""

    path: Path
    nodata: float | None = None


Layer = pd.DataFrame | RasterLayer


def _as_wgs84(layer: Layer) -> Layer:
    if isinstance(layer, gpd.GeoDataFrame):
        if layer.crs is None:
            return layer.set_crs(4326)
        if layer.crs.to_epsg() != 4326:
            return layer.to_crs(4326)
    return layer


def _layer_mask(hexes: pd.DataFrame, layer: pd.DataFrame, res: int) -> np.ndarray:
    """Hexes whose centroid lies within the layer's bounds (padded by two hex diameters), so a
    US tract overlay never touches the other ~590k hexes of the world."""
    if not isinstance(layer, gpd.GeoDataFrame) or layer.empty:
        return np.ones(len(hexes), dtype=bool)
    minx, miny, maxx, maxy = layer.total_bounds
    pad = h3util.pad_degrees(res)
    lng, lat = hexes["lng"].to_numpy(), hexes["lat"].to_numpy()
    return (lng >= minx - pad) & (lng <= maxx + pad) & (lat >= miny - pad) & (lat <= maxy + pad)


def _layer_near(layer: pd.DataFrame, chunk: pd.DataFrame, res: int) -> pd.DataFrame | None:
    """The layer rows whose bounds meet the chunk's hexes (centroids padded as in ``_layer_mask``),
    or None when there are none. Only a polygon layer is narrowed; the overlay result does not
    change, because a polygon that misses every hex of the chunk contributes nothing to it."""
    if not isinstance(layer, gpd.GeoDataFrame):
        return layer
    pad = h3util.pad_degrees(res)
    lng, lat = chunk["lng"].to_numpy(), chunk["lat"].to_numpy()
    box = shapely.box(lng.min() - pad, lat.min() - pad, lng.max() + pad, lat.max() + pad)
    hit = layer.sindex.query(box, predicate="intersects")
    if len(hit) == 0:
        return None
    return layer if len(hit) == len(layer) else layer.iloc[np.sort(hit)]


def run_joiner(spec: JoinSpec, hexes: pd.DataFrame, layer: Layer, res: int, field: str, bbox: BBox | None = None, cellset: h3util.CellSet | None = None) -> np.ndarray:
    """One joiner over the relevant subset of hexes; float array aligned to ``hexes`` rows."""
    out = np.full(len(hexes), np.nan, dtype="float64")
    if spec.joiner == "iso_lookup":
        v = JOINERS["iso_lookup"](hexes, layer, field)
        return pd.to_numeric(v, errors="coerce").to_numpy(dtype="float64")
    if spec.joiner == "raster_mean":
        # hex-level: every hex at once; the joiner reads only the windows inside `bbox`
        assert isinstance(layer, RasterLayer), f"{spec.source}: raster_mean needs a raster layer"
        v = JOINERS["raster_mean"](hexes, layer.path, res, band=spec.band, nodata=layer.nodata, decimate=spec.decimate, sample=spec.sample, bbox=bbox, cells=cellset if cellset is not None else hexes["h3"])
        return v.to_numpy(dtype="float64")
    if spec.joiner == "point_mean":
        v = JOINERS["point_mean"](hexes, layer, res, field, weight_field=spec.weight_field)
        return v.to_numpy(dtype="float64")
    if spec.joiner == "point_radius":
        v = JOINERS["point_radius"](hexes, layer, res, field, radius_km=spec.radius_km, agg=spec.agg, weight_field=spec.weight_field)
        return v.to_numpy(dtype="float64")
    mask = _layer_mask(hexes, layer, res)
    if not mask.any():
        return out
    sub = hexes[mask]
    if spec.joiner == "polygon_centroid":
        v = JOINERS["polygon_centroid"](sub, layer, field)
    elif spec.joiner == "area_weighted_overlay":
        # chunked so the intersection frame stays bounded (the US tract overlay peaked at 6 GB
        # for ~7k res-4 hexes; res 5 has four times as many)
        parts = []
        for i in range(0, len(sub), OVERLAY_CHUNK):
            chunk = sub.iloc[i : i + OVERLAY_CHUNK]
            near = _layer_near(layer, chunk, res)  # only the polygons this chunk can touch
            parts.append(pd.Series(np.nan, index=chunk.index) if near is None else JOINERS["area_weighted_overlay"](chunk, near, field, weight_field=spec.weight_field))
        v = pd.concat(parts) if len(parts) > 1 else parts[0]
    else:
        raise ValueError(f"{spec.source}: unknown joiner {spec.joiner!r}")
    out[mask] = pd.to_numeric(v, errors="coerce").to_numpy(dtype="float64")
    return out


def _largest_remainder(shares: np.ndarray) -> np.ndarray:
    """Round percentage rows to integers that sum to exactly 100 (largest-remainder method)."""
    floors = np.floor(shares)
    remainder = np.round(100 - floors.sum(axis=1)).astype(int)
    frac = shares - floors
    rank = np.argsort(np.argsort(-frac, axis=1, kind="stable"), axis=1, kind="stable")
    return (floors + (rank < remainder[:, None])).astype("int64")


# joiners that work on any subset of hexes; the hex-level ones read every hex against one cell set
_SUBSETTABLE = ("iso_lookup", "polygon_centroid", "area_weighted_overlay")


def allowed_countries(spec: JoinSpec, domain_countries: dict[str, tuple[str, ...]] | None) -> tuple[str, ...] | None:
    """ISO2 codes ``spec`` may fill, or None when it is not restricted (SPEC §20.4, §13.45)."""
    if spec.countries is not None:
        return spec.countries
    return None if domain_countries is None else domain_countries.get(spec.domain)


def _run_restricted(spec: JoinSpec, hexes: pd.DataFrame, layer: Layer, res: int, field: str, allow: np.ndarray | None, bbox: BBox | None, cellset: h3util.CellSet | None) -> np.ndarray:
    """``run_joiner`` limited to the hexes in ``allow`` (NaN elsewhere); None means every hex."""
    if allow is None:
        return run_joiner(spec, hexes, layer, res, field, bbox, cellset)
    out = np.full(len(hexes), np.nan, dtype="float64")
    if not allow.any():
        return out
    if spec.joiner in _SUBSETTABLE:
        out[allow] = run_joiner(spec, hexes[allow], layer, res, field, bbox, None)
    else:
        v = run_joiner(spec, hexes, layer, res, field, bbox, cellset)
        out[allow] = v[allow]
    return out


def join_dimension(dim: Dimension, hexes: pd.DataFrame, res: int, layers: LayerStore | dict[str, Layer | None], bbox: BBox | None = None, cellset: h3util.CellSet | None = None, domain_countries: dict[str, tuple[str, ...]] | None = None) -> dict[str, pd.Series]:
    """All output columns for one dimension, first-hit-wins across its joiners. A joiner whose
    domain belongs to one country (``domain_countries``) fills only that country's hexes."""
    n = len(hexes)
    iso = hexes["iso_a2"].fillna("").astype(str).to_numpy() if "iso_a2" in hexes.columns else None
    res_tag = np.full(n, "none", dtype=object)
    src = np.full(n, None, dtype=object)
    dom = np.full(n, None, dtype=object)
    lbl = np.full(n, None, dtype=object)
    comps = {k: np.full(n, np.nan) for k in COMPOSITION_KEYS} if dim.kind == "composition" else None
    raw = np.full(n, np.nan)
    for spec in dim.joiners:
        layer = layers.get(spec.source)
        if layer is None:
            continue  # source not available; reported by run()
        countries = allowed_countries(spec, domain_countries)
        allow = None if countries is None or iso is None else np.isin(iso, countries)
        if comps is not None:
            first = _run_restricted(spec, hexes, layer, res, spec.fields["w"], allow, bbox, cellset)
            fill = np.isnan(comps["w"]) & ~np.isnan(first)
            if not fill.any():
                continue
            comps["w"][fill] = first[fill]
            for k in COMPOSITION_KEYS[1:]:
                v = _run_restricted(spec, hexes, layer, res, spec.fields[k], allow, bbox, cellset)
                comps[k][fill] = v[fill]
        else:
            v = _run_restricted(spec, hexes, layer, res, spec.field, allow, bbox, cellset)
            fill = np.isnan(raw) & ~np.isnan(v)
            if not fill.any():
                continue
            raw[fill] = v[fill]
        res_tag[fill] = spec.res
        src[fill] = spec.source
        if spec.domain_by_country and iso is not None:
            # values relative within a country are ranked only against that country (§20.4)
            dom[fill] = np.where(iso[fill] != "", np.char.add(f"{spec.domain}:", iso[fill].astype(str)), spec.domain)
        else:
            dom[fill] = spec.domain
        lbl[fill] = spec.label or spec.source
    cols: dict[str, pd.Series] = {}
    if dim.kind == "score":
        cols[f"{dim.id}_raw"] = pd.Series(raw, dtype="float32")
    elif dim.kind == "signed":
        # §6.1: {id}_lean is an integer in -100..100; missing stays <NA>
        cols[f"{dim.id}_lean"] = pd.array(np.clip(np.round(raw), -100, 100), dtype="Int16")
    else:
        stack = np.column_stack([comps[k] for k in COMPOSITION_KEYS])
        complete = ~np.isnan(stack).any(axis=1)
        total = stack.sum(axis=1)
        complete &= total > 0
        pct = np.full(stack.shape, np.nan)
        if complete.any():
            pct[complete] = _largest_remainder(100.0 * stack[complete] / total[complete, None])
        for i, k in enumerate(COMPOSITION_KEYS):
            cols[f"{dim.id}_{k}"] = pd.array(pct[:, i], dtype="Int8")
        maj = np.full(n, "none", dtype=object)
        if complete.any():
            maj[complete] = np.array(COMPOSITION_KEYS, dtype=object)[np.argmax(pct[complete], axis=1)]
        cols[f"{dim.id}_maj"] = pd.Series(maj, dtype="object")
        # a hex that lacks any component is fully missing (invariant 3)
        res_tag[~complete] = "none"
        src[~complete] = None
        dom[~complete] = None
        lbl[~complete] = None
    cols[f"{dim.id}_res"] = pd.Series(res_tag, dtype="object")
    cols[f"{dim.id}_src"] = pd.Series(src, dtype="object")
    cols[f"{dim.id}_dom"] = pd.Series(dom, dtype="object")
    cols[f"{dim.id}_lbl"] = pd.Series(lbl, dtype="object")
    return cols


def check_nonnull(source_id: str, layer: pd.DataFrame, fields: set[str], minimum: float = MIN_NONNULL) -> None:
    """Stop early when a prepared layer is empty or a joiner field is mostly empty (SPEC §13.44):
    that is a broken download or a changed column, and scoring it would quietly show a gap. A
    ``min_nonnull:`` on the source in ``sources.yaml`` overrides the default (0 turns it off).
    A field the layer does not have is left to the joiner, which says so itself."""
    if minimum <= 0:
        return
    if len(layer) == 0:
        raise RuntimeError(f"dims: {source_id} prepared to a layer with no rows; check the download and its prep loader (set `min_nonnull: 0` on the source to allow it)")
    for field in sorted(fields):
        if field not in layer.columns:
            continue
        share = float(layer[field].notna().mean())
        if share < minimum:
            raise RuntimeError(
                f"dims: {source_id}.{field} is filled in {100 * share:.1f}% of {len(layer)} rows (minimum {100 * minimum:.0f}%); "
                f"the download or the prep loader is probably broken. If it is really that sparse, set `min_nonnull: {share:.2f}` or lower on the source in sources.yaml"
            )


class LayerStore:
    """The prepared layers of a ``dims`` run, loaded when first asked for and dropped after the
    last dimension that uses them (``done``). A real download that is not there is skipped with
    its recipe printed and reads as None, so the next joiner takes over. ``tried`` and
    ``skipped`` are shared across resolutions by the caller."""

    def __init__(self, settings: Settings, dims: list[Dimension], sources: dict[str, Source], tried: set[str], skipped: dict[str, str]):
        self.settings, self.sources, self.tried, self.skipped = settings, sources, tried, skipped
        self.uses = Counter(spec.source for d in dims for spec in d.joiners)
        self.fields: dict[str, set[str]] = {}
        self.first: dict[str, JoinSpec] = {}  # the first joiner naming a source decides how it loads
        for d in dims:
            for spec in d.joiners:
                self.first.setdefault(spec.source, spec)
                if spec.joiner == "raster_mean":
                    continue
                self.fields.setdefault(spec.source, set()).update(spec.fields.values() if spec.fields else [spec.field])
        self.layers: dict[str, Layer | None] = {}

    def get(self, source_id: str, default=None) -> Layer | None:
        if source_id not in self.layers:
            self.layers[source_id] = self._load(source_id)
        layer = self.layers[source_id]
        return default if layer is None else layer

    def _load(self, source_id: str) -> Layer | None:
        spec = self.first[source_id]
        self.tried.add(source_id)
        try:
            if spec.joiner == "raster_mean":
                nd = self.sources[source_id].extra.get("nodata")
                return RasterLayer(prep.load_raster(self.settings, source_id, self.sources), float(nd) if nd is not None else None)
            layer = _as_wgs84(prep.load_layer(self.settings, source_id, self.sources))
        except FileNotFoundError as exc:
            if source_id not in self.skipped:
                print(f"dims   skipping joiner source {source_id}: not available\n       " + str(exc).replace("\n", "\n       "))
            self.skipped[source_id] = str(exc)
            return None
        self.skipped.pop(source_id, None)
        check_nonnull(source_id, layer, self.fields.get(source_id, set()), float(self.sources[source_id].extra.get("min_nonnull", MIN_NONNULL)))
        return layer

    def done(self, dim: Dimension) -> None:
        """``dim`` is joined: free every layer no remaining dimension needs."""
        freed = False
        for spec in dim.joiners:
            self.uses[spec.source] -= 1
            if self.uses[spec.source] <= 0 and self.layers.pop(spec.source, None) is not None:
                freed = True
        if freed:
            gc.collect()  # GeoDataFrames carry reference cycles and cached spatial indexes


def _inputs(settings: Settings, dims: list[Dimension], sources: dict[str, Source], res: int) -> list:
    paths = [settings.hexes_path(res), settings.stage_path("pop", res), settings.stage_path("admin", res)]
    seen = set()
    for dim in dims:
        for spec in dim.joiners:
            if spec.source in seen:
                continue
            seen.add(spec.source)
            src = sources[spec.source]
            if src.access == "fixture":
                paths += [settings.raw(src.id) / f for f in src.files]
            else:
                paths += prep.raw_inputs(settings, src, sources)
    return paths


def _tag_counts(df: pd.DataFrame, inhabited: pd.Series, dims: list[Dimension]) -> dict[str, dict[str, int]]:
    out = {}
    for dim in dims:
        tags = df.loc[inhabited.to_numpy(dtype=bool), f"{dim.id}_res"].value_counts()
        out[dim.id] = {str(k): int(v) for k, v in tags.items()}
    return out


def _dim_inputs(settings: Settings, dim: Dimension, sources: dict[str, Source], res: int) -> list:
    return _inputs(settings, [dim], sources, res)


def _dim_spec(dim: Dimension, sources: dict[str, Source], domain_countries: dict[str, tuple[str, ...]] | None = None) -> str:
    """Digest of what the registry says about one dimension and its sources (name and note are
    display-only and do not change the parquet), plus the countries each joiner may fill."""
    used = sorted({spec.source for spec in dim.joiners})
    allowed = [allowed_countries(spec, domain_countries) for spec in dim.joiners]
    blob = repr(replace(dim, name="", note="")) + "".join(repr(sources[s]) for s in used) + repr(allowed)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def dim_fingerprints(settings: Settings, dims: list[Dimension], sources: dict[str, Source], res: int) -> dict[str, str]:
    """Per dimension: its inputs (the res's hexes, pop, admin and its own sources' raw files),
    its registry entry and the stage code. A plain ``dims`` run recomputes exactly the
    dimensions whose fingerprint moved (SPEC §13.39)."""
    params = {"res": res, "bbox": settings.bbox, "prep_version": prep.PREP_VERSION, "stage": "dims"}
    return {d.id: stage_cache.fingerprint(_dim_inputs(settings, d, sources, res), {**params, "dim": d.id, "spec": _dim_spec(d, sources, settings.domain_countries)}) for d in dims}


def _parts_dir(settings: Settings, res: int) -> Path:
    return settings.interim_dir / f"dims_r{res}.parts"


def _shard_key(settings: Settings, dim: Dimension, sources: dict[str, Source], res: int, base: dict) -> tuple[list, dict]:
    """The (inputs, params) a dimension's checkpoint shard is fingerprinted with: exactly what
    ``dim_fingerprints`` uses, so a shard is valid when and only when the dimension is fresh."""
    return _dim_inputs(settings, dim, sources, res), {**base, "dim": dim.id, "spec": _dim_spec(dim, sources, settings.domain_countries)}


def _adoptable(settings: Settings, dim: Dimension, sources: dict[str, Source], res: int, base: dict, rows: int) -> dict | None:
    """The checkpoint shard of ``dim`` when it is still valid (its recorded extras), else None."""
    shard = _parts_dir(settings, res) / f"{dim.id}.parquet"
    inputs, params = _shard_key(settings, dim, sources, res, base)
    if not stage_cache.is_fresh(shard, inputs, params):
        return None
    meta = stage_cache.read_meta(shard)
    return meta if meta.get("rows") == rows else None


def run(settings: Settings, only: list[str] | None = None) -> dict[int, dict[str, dict[str, int]]]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    all_dims = [d for d in load_dimensions(settings.dimensions_path, sources).values() if d.joiners and d.group != "hazard"]
    if only:
        unknown = sorted(set(only) - {d.id for d in all_dims})
        if unknown:
            raise ValueError(f"dims --only: unknown dimension id(s) {unknown}; known: {[d.id for d in all_dims]}")
    tried: set[str] = set()  # sources this run attempted to load (anything else keeps its recorded state)
    skipped: dict[str, str] = {}
    counts: dict[int, dict[str, dict[str, int]]] = {}
    for res in settings.res:
        for p in (settings.hexes_path(res), settings.stage_path("pop", res), settings.stage_path("admin", res)):
            if not p.exists():
                raise FileNotFoundError(f"{p} missing (run `grid`, `pop` and `admin` first)")
        out = settings.stage_path("dims", res)
        inputs = _inputs(settings, all_dims, sources, res)
        params = {"res": res, "bbox": settings.bbox, "prep_version": prep.PREP_VERSION, "stage": "dims"}
        want = dim_fingerprints(settings, all_dims, sources, res)
        meta = stage_cache.read_meta(out) if out.exists() else {}
        intact = bool(meta) and meta.get("output_bytes") in (None, out.stat().st_size)  # not replaced since recorded
        have: dict[str, str] = meta.get("dims", {}) if intact and not settings.force else {}
        if only:
            if not out.exists():
                raise FileNotFoundError(f"dims --only needs an existing {out.name}; run `dims` without --only first")
            todo = [d for d in all_dims if d.id in set(only)]
        else:
            todo = [d for d in all_dims if have.get(d.id) != want[d.id]]
        if not todo:
            df = pd.read_parquet(out, columns=[f"{d.id}_res" for d in all_dims])  # tags only, not the whole width
            inhabited = pd.read_parquet(settings.stage_path("pop", res), columns=["inhabited"])["inhabited"]
            counts[res] = _tag_counts(df, inhabited, all_dims)
            print(f"dims   res {res}: up to date ({len(df)} hexes), skipping")
            if not only:
                shutil.rmtree(_parts_dir(settings, res), ignore_errors=True)  # checkpoints of a forced run that died: the final file is good
            continue
        existing: pd.DataFrame | None = None
        if len(todo) < len(all_dims):
            existing = pd.read_parquet(out)
            drop = tuple(f"{d.id}_" for d in todo)
            existing = existing[[c for c in existing.columns if c == "h3" or not c.startswith(drop)]]
            if not only:
                print(f"dims   res {res}: {len(todo)} of {len(all_dims)} dimensions changed ({', '.join(d.id for d in todo)}); the rest are up to date")
        t0 = time.time()
        hexes = (
            pd.read_parquet(settings.hexes_path(res), columns=["h3", "lat", "lng"])
            .merge(pd.read_parquet(settings.stage_path("pop", res)), on="h3", how="left")
            .merge(pd.read_parquet(settings.stage_path("admin", res), columns=["h3", "iso_a2"]), on="h3", how="left")
            .reset_index(drop=True)
        )
        parts, base = _parts_dir(settings, res), params
        if settings.force:
            shutil.rmtree(parts, ignore_errors=True)
        resumed: dict[str, dict] = {}
        if not only and not settings.force:
            resumed = {d.id: m for d in todo if (m := _adoptable(settings, d, sources, res, base, len(hexes))) is not None}
        compute = [d for d in todo if d.id not in resumed]
        store = LayerStore(settings, compute, sources, tried, skipped)
        needs_cells = any(spec.joiner == "raster_mean" for d in compute for spec in d.joiners)
        cellset = h3util.CellSet.from_cells(hexes["h3"]) if needs_cells else None  # built once, not per raster dimension
        cols: dict[str, pd.Series] = {}
        for dim in todo:  # registry order, so the columns come out in the same order with or without a resume
            t1 = time.time()
            if dim.id in resumed:
                shard = pd.read_parquet(parts / f"{dim.id}.parquet")
                cols.update({c: shard[c] for c in shard.columns})
                tried.update(spec.source for spec in dim.joiners)
                skipped.update(resumed[dim.id].get("skipped_sources", {}))
                print(f"dims   res {res}: {dim.id:8s} resumed from checkpoint")
                continue
            got = join_dimension(dim, hexes, res, store, settings.bbox, cellset, settings.domain_countries)
            store.done(dim)
            cols.update(got)
            if not only:  # a --only run is a small, deliberate edit; it neither writes nor deletes checkpoints
                # a crash later in this run keeps this dimension (see the module docstring)
                parts.mkdir(parents=True, exist_ok=True)
                shard_path = parts / f"{dim.id}.parquet"
                with stage_cache.atomic_path(shard_path) as tmp:
                    pd.DataFrame(got, index=hexes.index).to_parquet(tmp, index=False)
                inputs_d, params_d = _shard_key(settings, dim, sources, res, base)
                stage_cache.record(shard_path, inputs_d, params_d, {"rows": len(hexes), "skipped_sources": {src: skipped[src] for src in {sp.source for sp in dim.joiners} if src in skipped}})
            tags = got[f"{dim.id}_res"][hexes["inhabited"].to_numpy(dtype=bool)].value_counts(normalize=True)
            shares = " ".join(f"{k} {100 * v:.1f}%" for k, v in tags.items())
            print(f"dims   res {res}: {dim.id:8s} {shares} ({time.time() - t1:.1f}s)")
        # one concat instead of a column insert per field (a fragmented frame on millions of rows)
        new = pd.DataFrame(cols, index=hexes.index)
        if existing is not None:
            # the recomputed columns sit beside the kept ones, row for row (same hex set and order)
            if len(existing) != len(new) or not existing["h3"].reset_index(drop=True).equals(hexes["h3"]):
                raise ValueError(f"{out.name} covers a different hex set than the current grid; run `dims` without --only")
            df = pd.concat([existing.reset_index(drop=True), new], axis=1)
        else:
            df = pd.concat([pd.DataFrame({"h3": hexes["h3"]}), new], axis=1)
        with stage_cache.atomic_path(out) as tmp:
            df.to_parquet(tmp, index=False)
        recorded = {k: v for k, v in have.items() if k in want} if existing is not None else {}
        recorded.update({d.id: want[d.id] for d in todo})
        # sources this run did not try keep their recorded state (validate reads it to tell a
        # missing download from a layer that loaded and came out empty)
        carried = {s: why for s, why in meta.get("skipped_sources", {}).items() if s not in tried} if existing is not None else {}
        used = {spec.source for d in all_dims for spec in d.joiners}
        used_skips = {s: why for s, why in {**carried, **skipped}.items() if s in used}
        stage_cache.record(out, inputs, params, {"rows": len(df), "skipped_sources": used_skips, "dims": recorded, "partial": sorted(only) if only else None})
        if not only:
            shutil.rmtree(parts, ignore_errors=True)  # the checkpoints did their job
        inhabited_all = pd.read_parquet(settings.stage_path("pop", res), columns=["h3", "inhabited"]).set_index("h3")["inhabited"].reindex(df["h3"]).to_numpy(dtype=bool)
        counts[res] = _tag_counts(df, pd.Series(inhabited_all), all_dims)
        what = f"{len(todo)} of {len(all_dims)} dimensions" + (" (--only)" if only else "")
        print(f"dims   res {res}: {what} on {len(df)} hexes in {time.time() - t0:.1f}s -> {out.name}")
        del hexes, cols, new, df, existing, store, cellset, resumed, compute  # the next resolution starts from an empty heap
        gc.collect()
    if skipped:
        print(f"dims   note: {len(skipped)} source(s) unavailable, fallbacks used: {', '.join(skipped)}")
    return counts
