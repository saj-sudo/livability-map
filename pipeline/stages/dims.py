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
"""

from __future__ import annotations

import hashlib
import time

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import h3util, prep, stage_cache
from ..config import Settings
from ..joiners import JOINERS
from ..registry import COMPOSITION_KEYS, Dimension, JoinSpec, Source, load_dimensions, load_sources


def _as_wgs84(layer: pd.DataFrame) -> pd.DataFrame:
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


def run_joiner(spec: JoinSpec, hexes: pd.DataFrame, layer: pd.DataFrame, res: int, field: str) -> np.ndarray:
    """One joiner over the relevant subset of hexes; float array aligned to ``hexes`` rows."""
    out = np.full(len(hexes), np.nan, dtype="float64")
    if spec.joiner == "iso_lookup":
        v = JOINERS["iso_lookup"](hexes, layer, field)
        return pd.to_numeric(v, errors="coerce").to_numpy(dtype="float64")
    mask = _layer_mask(hexes, layer, res)
    if not mask.any():
        return out
    sub = hexes[mask]
    if spec.joiner == "polygon_centroid":
        v = JOINERS["polygon_centroid"](sub, layer, field)
    elif spec.joiner == "area_weighted_overlay":
        v = JOINERS["area_weighted_overlay"](sub, layer, field, weight_field=spec.weight_field)
    else:  # point_density
        v = JOINERS["point_density"](sub, layer, res, per_capita=spec.per_capita)
    out[mask] = pd.to_numeric(v, errors="coerce").to_numpy(dtype="float64")
    return out


def _largest_remainder(shares: np.ndarray) -> np.ndarray:
    """Round percentage rows to integers that sum to exactly 100 (largest-remainder method)."""
    floors = np.floor(shares)
    remainder = np.round(100 - floors.sum(axis=1)).astype(int)
    frac = shares - floors
    rank = np.argsort(np.argsort(-frac, axis=1, kind="stable"), axis=1, kind="stable")
    return (floors + (rank < remainder[:, None])).astype("int64")


def join_dimension(dim: Dimension, hexes: pd.DataFrame, res: int, layers: dict[str, pd.DataFrame | None]) -> dict[str, pd.Series]:
    """All output columns for one dimension, first-hit-wins across its joiners."""
    n = len(hexes)
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
        if comps is not None:
            first = run_joiner(spec, hexes, layer, res, spec.fields["w"])
            fill = np.isnan(comps["w"]) & ~np.isnan(first)
            if not fill.any():
                continue
            comps["w"][fill] = first[fill]
            for k in COMPOSITION_KEYS[1:]:
                v = run_joiner(spec, hexes, layer, res, spec.fields[k])
                comps[k][fill] = v[fill]
        else:
            v = run_joiner(spec, hexes, layer, res, spec.field)
            fill = np.isnan(raw) & ~np.isnan(v)
            if not fill.any():
                continue
            raw[fill] = v[fill]
        res_tag[fill] = spec.res
        src[fill] = spec.source
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


def _load_layers(settings: Settings, dims: list[Dimension], sources: dict[str, Source]) -> tuple[dict[str, pd.DataFrame | None], dict[str, str]]:
    """Every joiner source once; missing real downloads become None with the reason kept."""
    layers: dict[str, pd.DataFrame | None] = {}
    skipped: dict[str, str] = {}
    for dim in dims:
        for spec in dim.joiners:
            if spec.source in layers:
                continue
            try:
                layers[spec.source] = _as_wgs84(prep.load_layer(settings, spec.source, sources))
            except FileNotFoundError as exc:
                layers[spec.source] = None
                skipped[spec.source] = str(exc)
                print(f"dims   skipping joiner source {spec.source}: not available\n       " + str(exc).replace("\n", "\n       "))
    return layers, skipped


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


def run(settings: Settings) -> dict[int, dict[str, dict[str, int]]]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    dims = [d for d in load_dimensions(settings.dimensions_path, sources).values() if d.joiners and d.group != "hazard"]
    yaml_sha = hashlib.sha256(settings.dimensions_path.read_bytes()).hexdigest()[:16]
    layers: dict[str, pd.DataFrame | None] | None = None
    skipped: dict[str, str] = {}
    counts: dict[int, dict[str, dict[str, int]]] = {}
    for res in settings.res:
        for p in (settings.hexes_path(res), settings.stage_path("pop", res), settings.stage_path("admin", res)):
            if not p.exists():
                raise FileNotFoundError(f"{p} missing (run `grid`, `pop` and `admin` first)")
        out = settings.stage_path("dims", res)
        inputs = _inputs(settings, dims, sources, res)
        params = {"res": res, "bbox": settings.bbox, "dimensions_sha": yaml_sha, "prep_version": prep.PREP_VERSION, "stage": "dims"}
        if stage_cache.is_fresh(out, inputs, params, settings.force):
            df = pd.read_parquet(out)
            inhabited = pd.read_parquet(settings.stage_path("pop", res), columns=["inhabited"])["inhabited"]
            counts[res] = _tag_counts(df, inhabited, dims)
            print(f"dims   res {res}: up to date ({len(df)} hexes), skipping")
            continue
        t0 = time.time()
        hexes = (
            pd.read_parquet(settings.hexes_path(res), columns=["h3", "lat", "lng"])
            .merge(pd.read_parquet(settings.stage_path("pop", res)), on="h3", how="left")
            .merge(pd.read_parquet(settings.stage_path("admin", res), columns=["h3", "iso_a2"]), on="h3", how="left")
            .reset_index(drop=True)
        )
        if layers is None:
            layers, skipped = _load_layers(settings, dims, sources)
        df = pd.DataFrame({"h3": hexes["h3"]})
        for dim in dims:
            t1 = time.time()
            for col, series in join_dimension(dim, hexes, res, layers).items():
                df[col] = series
            tags = df.loc[hexes["inhabited"].to_numpy(dtype=bool), f"{dim.id}_res"].value_counts(normalize=True)
            shares = " ".join(f"{k} {100 * v:.1f}%" for k, v in tags.items())
            print(f"dims   res {res}: {dim.id:8s} {shares} ({time.time() - t1:.1f}s)")
        df.to_parquet(out, index=False)
        stage_cache.record(out, inputs, params, {"rows": len(df), "skipped_sources": skipped})
        counts[res] = _tag_counts(df, hexes["inhabited"], dims)
        print(f"dims   res {res}: {len(dims)} dimensions on {len(df)} hexes in {time.time() - t0:.1f}s -> {out.name}")
    if skipped:
        print(f"dims   note: {len(skipped)} source(s) unavailable, fallbacks used: {', '.join(skipped)}")
    return counts
