"""``urban`` stage (SPEC §5, §13.31): GHS-SMOD degree-of-urbanisation classes -> urban polygons.

Writes ``data/interim/urban.parquet`` (GeoParquet) with one row per polygon: ``uc_id`` (ordinal
by area within its kind, 1 = largest), ``kind`` (``centre`` = class 30, ``cluster`` = class >= 21,
which includes the centres), ``area_km2`` (EPSG:6933) and the WGS84 geometry. The ``grid`` stage
refines parent cells that touch these polygons (resolution plan ``where: {urban: kind}``);
Session 11 reuses the same layer for block hexes, which is why it is saved with ids rather than
kept in memory.

The raster is read window by window (``h3util.iter_windows``); each window's class mask is
polygonised with ``rasterio.features.shapes`` and the pieces are unioned at the end so a town
that straddles a window edge is still one polygon with one id.
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio import features
from shapely.geometry import shape

from .. import h3util, rawfiles, stage_cache
from ..config import BBox, Settings
from ..registry import load_sources

SMOD_SOURCE = "ghsl_smod"
KINDS = {"centre": 30, "cluster": 21}  # kind -> minimum GHS-SMOD class


def _empty(kind: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"uc_id": pd.Series(dtype="int64"), "kind": pd.Series(dtype=str), "area_km2": pd.Series(dtype="float64")}, geometry=[], crs=4326)


def polygons_from_raster(path: Path, bbox: BBox | None = None, nodata: float | None = None, window_size: int = 2048) -> gpd.GeoDataFrame:
    """Urban centre and cluster polygons from a GHS-SMOD class raster (EPSG:4326)."""
    pieces: dict[str, list] = {k: [] for k in KINDS}
    with rasterio.open(path) as src:
        nd = nodata if nodata is not None else src.nodata
        for window in h3util.iter_windows(src, bbox, window_size):
            arr = src.read(1, window=window)
            valid = h3util._mask_valid(arr.astype("float64"), nd)
            transform = src.window_transform(window)
            for kind, lo in KINDS.items():
                mask = valid & (arr >= lo)
                if not mask.any():
                    continue
                for geom, _ in features.shapes(mask.astype("uint8"), mask=mask, transform=transform):
                    pieces[kind].append(shape(geom))
    frames = []
    for kind in KINDS:
        if not pieces[kind]:
            frames.append(_empty(kind))
            continue
        merged = shapely.unary_union(pieces[kind])  # joins pieces that met at window edges
        polys = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        gdf = gpd.GeoDataFrame({"kind": [kind] * len(polys)}, geometry=polys, crs=4326)
        gdf["area_km2"] = gdf.to_crs(6933).area / 1e6
        gdf = gdf.sort_values("area_km2", ascending=False, kind="stable").reset_index(drop=True)
        gdf.insert(0, "uc_id", np.arange(1, len(gdf) + 1, dtype="int64"))
        frames.append(gdf)
    out = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(out[["uc_id", "kind", "area_km2", "geometry"]], geometry="geometry", crs=4326)


def run(settings: Settings) -> dict[str, int]:
    settings.ensure_dirs()
    src = load_sources(settings.sources_path)[SMOD_SOURCE]
    raster = rawfiles.resolve_raster(settings, src)  # extracts the zip member once
    out = settings.urban_path
    params = {"stage": "urban", "bbox": settings.bbox, "kinds": KINDS}
    if stage_cache.is_fresh(out, [raster], params, settings.force):
        counts = stage_cache.read_meta(out).get("counts", {})
        print(f"urban  up to date ({counts}), skipping")
        return {k: int(counts.get(k, 0)) for k in KINDS}
    t0 = time.time()
    nd = src.extra.get("nodata")
    gdf = polygons_from_raster(raster, settings.bbox, None if nd is None else float(nd))
    gdf.to_parquet(out, index=False)
    counts = {k: int((gdf["kind"] == k).sum()) for k in KINDS}
    stage_cache.record(out, [raster], params, {"counts": counts})
    print(f"urban  {counts['centre']} urban centres, {counts['cluster']} urban clusters in {time.time() - t0:.1f}s -> {out.name}")
    return counts
