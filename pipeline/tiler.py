"""Windows-native vector tiler: hex parquet -> PMTiles archive (SPEC §9.2, decision §13.18).

tippecanoe cannot run on Windows, so this module does the job in Python: every hex polygon is
projected to the Web Mercator unit square, assigned to the XYZ tiles it touches per zoom,
clipped to the tile (plus buffer), encoded with ``mapbox-vector-tile`` and gzipped, and the
tiles are written in Hilbert order with the ``pmtiles`` writer. Workers (multiprocessing, spawn
on Windows) each load the layer once and encode batches of tiles; only tile addresses and index
arrays cross the process boundary.

Facts this code relies on (checked 2026-09-22): ``mapbox_vector_tile.encode`` keeps only native
``str | bool | int | float`` property values and silently drops numpy scalars and ``None``;
``quantize_bounds`` is a linear map so buffer coordinates outside ``[0, extent)`` pass through;
``pmtiles.writer.Writer`` sorts entries itself but flags the archive unclustered when tile ids
arrive out of order, and deduplicates identical tiles by hash.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import shapely
from shapely import GeometryType

EXTENT = 4096
BUFFER = 80  # tile units (~2% of the tile, like tippecanoe's default 5/256)
MAX_LAT = 85.05112878  # Web Mercator limit
BATCH = 64


@dataclass(frozen=True)
class LayerSpec:
    name: str  # "hex4"
    parquet: Path
    minzoom: int
    maxzoom: int
    attrs: tuple[str, ...]  # attributes shipped at every zoom
    slim_attrs: tuple[str, ...] = ()  # subset for zooms below slim_below_zoom
    slim_below_zoom: int | None = None
    description: str = ""


@dataclass
class Rings:
    coords: np.ndarray  # (N, 2) unit-square x, y
    offsets: np.ndarray  # (M + 1,) ring start offsets into coords
    row_of: np.ndarray  # (M,) parquet row index per ring (antimeridian cells contribute two rings)


# ---- projection ---------------------------------------------------------------------------------


def project_unit(lng: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Web Mercator unit square: x in [0, 1] west->east, y in [0, 1] north->south."""
    lat = np.clip(np.asarray(lat, dtype="float64"), -MAX_LAT, MAX_LAT)
    s = np.sin(np.radians(lat))
    x = (np.asarray(lng, dtype="float64") + 180.0) / 360.0
    y = 0.5 - np.log((1.0 + s) / (1.0 - s)) / (4.0 * np.pi)
    return x, y


def lnglat_to_tile(lng: float, lat: float, z: int) -> tuple[int, int]:
    x, y = project_unit(np.array([lng]), np.array([lat]))
    n = 1 << z
    return int(min(n - 1, max(0, math.floor(x[0] * n)))), int(min(n - 1, max(0, math.floor(y[0] * n))))


def split_antimeridian(ring: list[tuple[float, float]]) -> list[shapely.Polygon]:
    """A lng/lat ring as one polygon, or two when it crosses +-180 (each within [-180, 180])."""
    arr = np.asarray(ring, dtype="float64")
    lng, lat = arr[:, 0], arr[:, 1]
    if lng.max() - lng.min() <= 180.0:
        return [shapely.Polygon(arr)]
    lng = np.where(lng < 0, lng + 360.0, lng)  # unwrap eastwards: values in (180 - eps, 360)
    east = shapely.Polygon(np.column_stack([lng, lat]))
    west = shapely.Polygon(np.column_stack([lng - 360.0, lat]))
    parts = []
    for poly in (east, west):
        clipped = shapely.clip_by_rect(poly, -180.0, -90.0, 180.0, 90.0)
        if not clipped.is_empty:
            parts.append(clipped)
    return parts


def cell_rings(cells: list[str]) -> Rings:
    """Unit-square rings for every cell; antimeridian cells yield two rings, polar-cap cells
    (centroid beyond the Mercator limit) yield none."""
    coords, offsets, row_of = [], [0], []
    for i, c in enumerate(cells):
        clat, _ = h3.cell_to_latlng(c)
        if abs(clat) > MAX_LAT:
            continue
        boundary = np.asarray(h3.cell_to_boundary(c), dtype="float64")  # (k, 2) lat, lng
        lat, lng = boundary[:, 0], boundary[:, 1]
        shifts = (0.0,)
        if lng.max() - lng.min() > 180.0:
            lng = np.where(lng < 0, lng + 360.0, lng)
            shifts = (0.0, -1.0)  # x > 1 copy and its west twin; clip_by_rect drops the off-world halves
        x, y = project_unit(lng, lat)
        for shift in shifts:
            ring = np.column_stack([x + shift, y])
            ring = np.vstack([ring, ring[:1]])  # close the ring
            coords.append(ring)
            offsets.append(offsets[-1] + len(ring))
            row_of.append(i)
    if not coords:
        return Rings(np.zeros((0, 2)), np.array([0]), np.zeros(0, dtype="int64"))
    return Rings(np.concatenate(coords), np.asarray(offsets, dtype="int64"), np.asarray(row_of, dtype="int64"))


def ring_polygons(rings: Rings) -> np.ndarray:
    """Shapely polygons (unit-square coordinates), one per ring, built vectorised."""
    m = len(rings.row_of)
    if m == 0:
        return np.array([], dtype=object)
    return shapely.from_ragged_array(GeometryType.POLYGON, rings.coords, offsets=(rings.offsets, np.arange(m + 1)))


def ring_bboxes(rings: Rings) -> np.ndarray:
    m = len(rings.row_of)
    out = np.zeros((m, 4))
    for i in range(m):
        seg = rings.coords[rings.offsets[i] : rings.offsets[i + 1]]
        out[i] = (seg[:, 0].min(), seg[:, 1].min(), seg[:, 0].max(), seg[:, 1].max())
    return out


# ---- tile assignment ------------------------------------------------------------------------------


def assign_tiles(bbox: np.ndarray, z: int, buffer_units: int = BUFFER) -> dict[tuple[int, int], np.ndarray]:
    """bbox: (M, 4) unit-square boxes. Returns {(x, y): ring indices} for every tile a box
    (plus buffer) touches. A hex never spans more than 2x2 tiles at the zooms used here."""
    n = 1 << z
    b = buffer_units / EXTENT / n
    tx0 = np.clip(np.floor((bbox[:, 0] - b) * n), 0, n - 1).astype("int64")
    ty0 = np.clip(np.floor((bbox[:, 1] - b) * n), 0, n - 1).astype("int64")
    tx1 = np.clip(np.floor((bbox[:, 2] + b) * n), 0, n - 1).astype("int64")
    ty1 = np.clip(np.floor((bbox[:, 3] + b) * n), 0, n - 1).astype("int64")
    keys, rows = [], []
    for dx in (0, 1, 2):
        for dy in (0, 1, 2):
            m = (tx0 + dx <= tx1) & (ty0 + dy <= ty1)
            if not m.any():
                continue
            keys.append((tx0[m] + dx) * n + (ty0[m] + dy))
            rows.append(np.nonzero(m)[0])
    if not keys:
        return {}
    keys, rows = np.concatenate(keys), np.concatenate(rows)
    order = np.argsort(keys, kind="stable")
    keys, rows = keys[order], rows[order]
    uniq, start = np.unique(keys, return_index=True)
    ends = np.r_[start[1:], len(keys)]
    return {(int(k // n), int(k % n)): rows[s:e] for k, s, e in zip(uniq, start, ends, strict=True)}


# ---- properties -----------------------------------------------------------------------------------

_DECIMALS = {"heat_days": 1, "rflood_frac": 3, "cflood_frac": 3, "wb_value": 3}


def column_objects(df: pd.DataFrame, names: list[str]) -> dict[str, np.ndarray]:
    """Each attribute as an object array of native Python scalars, None where missing, floats
    rounded (the MVT encoder drops numpy scalars and None silently, so this matters)."""
    out: dict[str, np.ndarray] = {}
    n = len(df)
    for name in names:
        if name not in df.columns:
            continue
        s = df[name]
        obj = np.full(n, None, dtype=object)
        missing = s.isna().to_numpy()
        valid = ~missing
        if not valid.any():
            out[name] = obj
            continue
        kind = s.dtype
        if str(kind) == "bool" or (str(kind).startswith("bool")):
            obj[valid] = s.to_numpy()[valid].astype(bool).tolist()
        elif str(kind).startswith(("Int", "int", "UInt", "uint")):
            obj[valid] = s[valid].astype("int64").to_numpy().tolist()
        elif str(kind).startswith(("float", "Float")):
            vals = s[valid].astype("float64").to_numpy()
            obj[valid] = np.round(vals, _DECIMALS.get(name, 3)).tolist()
        else:
            obj[valid] = [str(v) for v in s[valid].tolist()]
        out[name] = obj
    return out


def props_for_rows(cols: dict[str, np.ndarray], names: list[str], rows: np.ndarray) -> list[dict]:
    present = [k for k in names if k in cols]
    out = []
    for r in rows:
        d = {}
        for k in present:
            v = cols[k][r]
            if v is not None:
                d[k] = v
        out.append(d)
    return out


# ---- encoding -------------------------------------------------------------------------------------


def encode_tile(z: int, x: int, y: int, geoms: np.ndarray, props: list[dict], layer: str, extent: int = EXTENT, buffer_units: int = BUFFER) -> bytes | None:
    """One gzipped MVT tile, or None when nothing intersects the (buffered) tile."""
    import mapbox_vector_tile

    n = 1 << z
    tx0, ty0, tx1, ty1 = x / n, y / n, (x + 1) / n, (y + 1) / n
    b = buffer_units / extent / n
    clipped = shapely.clip_by_rect(geoms, tx0 - b, ty0 - b, tx1 + b, ty1 + b)
    keep = ~shapely.is_empty(clipped)
    if not keep.any():
        return None
    feats = [{"geometry": g, "properties": p} for g, p in zip(clipped[keep], (props[i] for i in np.nonzero(keep)[0]), strict=True)]
    raw = mapbox_vector_tile.encode(
        [{"name": layer, "features": feats}],
        default_options={"extents": extent, "quantize_bounds": (tx0, ty0, tx1, ty1), "y_coord_down": True},
    )
    return gzip.compress(raw, compresslevel=6, mtime=0)


# ---- worker state -----------------------------------------------------------------------------------

_LAYERS: dict[str, dict] = {}


def _load_layer(spec: LayerSpec) -> dict:
    names = sorted(set(spec.attrs) | set(spec.slim_attrs) | {"h3"})
    df = pd.read_parquet(spec.parquet)
    df = df[[c for c in names if c in df.columns]]
    rings = cell_rings(df["h3"].tolist())
    return {"spec": spec, "geoms": ring_polygons(rings), "row_of": rings.row_of, "cols": column_objects(df, names), "rows": len(df)}


def _init_worker(specs: list[LayerSpec]) -> None:
    global _LAYERS
    _LAYERS = {spec.name: _load_layer(spec) for spec in specs}


def _encode_batch(batch: list[tuple[str, int, int, int, np.ndarray]]) -> list[tuple[int, int, bytes, int]]:
    from pmtiles.tile import zxy_to_tileid

    out = []
    for layer_name, z, x, y, ring_idx in batch:
        L = _LAYERS[layer_name]
        spec: LayerSpec = L["spec"]
        names = list(spec.slim_attrs) if spec.slim_below_zoom is not None and z < spec.slim_below_zoom and spec.slim_attrs else list(spec.attrs)
        rows = L["row_of"][ring_idx]
        props = props_for_rows(L["cols"], names, rows)
        data = encode_tile(z, x, y, L["geoms"][ring_idx], props, layer_name)
        if data is not None:
            out.append((zxy_to_tileid(z, x, y), z, data, int(len(rows))))
    return out


# ---- driver -------------------------------------------------------------------------------------------


@dataclass
class TileReport:
    tiles: int = 0
    features: int = 0
    bytes: int = 0
    sha256: str = ""
    seconds: float = 0.0
    per_zoom: dict[int, list[int]] = field(default_factory=dict)  # z -> [tiles, bytes]
    largest: tuple[int, int, int, int] = (0, 0, 0, 0)  # z, x, y, bytes
    layers: list[dict] = field(default_factory=list)


def _field_types(df: pd.DataFrame, names: tuple[str, ...]) -> dict[str, str]:
    types = {}
    for n in names:
        if n not in df.columns:
            continue
        k = str(df[n].dtype)
        types[n] = "Boolean" if k.startswith("bool") else "Number" if k[0] in "iIuUfF" else "String"
    return types


def build_pmtiles(layers: list[LayerSpec], out: Path, *, workers: int | None = None, bounds: tuple[float, float, float, float] | None = None, metadata_extra: dict | None = None) -> TileReport:
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer

    t0 = time.time()
    report = TileReport()
    tasks: list[tuple[int, str, int, int, int, np.ndarray]] = []
    all_bounds = []
    for spec in layers:
        df = pd.read_parquet(spec.parquet, columns=["h3"])
        rings = cell_rings(df["h3"].tolist())
        bbox = ring_bboxes(rings)
        if len(bbox):
            all_bounds.append((bbox[:, 0].min(), bbox[:, 1].min(), bbox[:, 2].max(), bbox[:, 3].max()))
        for z in range(spec.minzoom, spec.maxzoom + 1):
            for (x, y), idx in assign_tiles(bbox, z).items():
                tasks.append((zxy_to_tileid(z, x, y), spec.name, z, x, y, idx))
        full_df = pd.read_parquet(spec.parquet)
        report.layers.append({"name": spec.name, "minzoom": spec.minzoom, "maxzoom": spec.maxzoom, "features": int(len(df)), "fields": _field_types(full_df, spec.attrs), "slim_below_zoom": spec.slim_below_zoom, "description": spec.description})
    tasks.sort(key=lambda t: t[0])  # Hilbert order -> clustered archive
    batches = [[t[1:] for t in tasks[i : i + BATCH]] for i in range(0, len(tasks), BATCH)]

    def _min_max():
        if bounds:
            return bounds
        if not all_bounds:
            return (-180.0, -85.0, 180.0, 85.0)
        x0 = min(b[0] for b in all_bounds)
        y0 = min(b[1] for b in all_bounds)
        x1 = max(b[2] for b in all_bounds)
        y1 = max(b[3] for b in all_bounds)
        lng0, lng1 = max(-180.0, x0 * 360 - 180), min(180.0, x1 * 360 - 180)
        lat1 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y0))))
        lat0 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y1))))
        return (lng0, lat0, lng1, lat1)

    minzoom = min(s.minzoom for s in layers)
    maxzoom = max(s.maxzoom for s in layers)
    lng0, lat0, lng1, lat1 = _min_max()
    header = {
        "tile_type": TileType.MVT,
        "tile_compression": Compression.GZIP,
        "min_lon_e7": int(round(lng0 * 1e7)),
        "min_lat_e7": int(round(lat0 * 1e7)),
        "max_lon_e7": int(round(lng1 * 1e7)),
        "max_lat_e7": int(round(lat1 * 1e7)),
        "center_zoom": minzoom,
        "center_lon_e7": int(round((lng0 + lng1) / 2 * 1e7)),
        "center_lat_e7": int(round((lat0 + lat1) / 2 * 1e7)),
    }
    metadata = {
        "name": "livability-map hexes",
        "format": "pbf",
        "type": "overlay",
        "description": f"H3 hexes {[s.name for s in layers]} zoom {minzoom}-{maxzoom}",
        "vector_layers": [{"id": L["name"], "description": L["description"], "minzoom": L["minzoom"], "maxzoom": L["maxzoom"], "fields": L["fields"]} for L in report.layers],
    }
    if metadata_extra:
        metadata.update(metadata_extra)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".pmtiles.part")
    use_pool = (workers is None or workers > 1) and len(tasks) >= 500 and workers != 0
    with open(tmp, "wb") as fh:
        writer = Writer(fh)
        if use_pool:
            pool = ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1), initializer=_init_worker, initargs=(layers,))
            results = pool.map(_encode_batch, batches, chunksize=1)
        else:
            _init_worker(layers)
            results = map(_encode_batch, batches)
        try:
            for res in results:
                for tileid, z, data, nfeat in res:
                    writer.write_tile(tileid, data)
                    report.tiles += 1
                    report.features += nfeat
                    pz = report.per_zoom.setdefault(z, [0, 0])
                    pz[0] += 1
                    pz[1] += len(data)
                    if len(data) > report.largest[3]:
                        xy = _tile_xy_from_id(tileid, z)
                        report.largest = (z, xy[0], xy[1], len(data))
        finally:
            if use_pool:
                pool.shutdown()
        writer.finalize(header, metadata)
    tmp.replace(out)
    report.bytes = out.stat().st_size
    report.sha256 = hashlib.sha256(out.read_bytes()).hexdigest()
    report.seconds = time.time() - t0
    return report


def _tile_xy_from_id(tileid: int, z: int) -> tuple[int, int]:
    from pmtiles.tile import tileid_to_zxy

    _, x, y = tileid_to_zxy(tileid)
    return x, y


def report_json(report: TileReport) -> dict:
    return {
        "tiles": report.tiles,
        "features": report.features,
        "bytes": report.bytes,
        "sha256": report.sha256,
        "seconds": round(report.seconds, 1),
        "per_zoom": {str(z): v for z, v in sorted(report.per_zoom.items())},
        "largest": {"z": report.largest[0], "x": report.largest[1], "y": report.largest[2], "bytes": report.largest[3]},
        "layers": report.layers,
    }


def write_report(path: Path, report: TileReport) -> None:
    path.write_text(json.dumps(report_json(report), indent=2), encoding="utf-8")
