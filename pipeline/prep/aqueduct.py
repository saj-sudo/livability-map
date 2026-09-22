"""Aqueduct 4.0 baseline drought risk -> polygons for ``polygon_centroid`` (SPEC §20.6 `drought`).

The same File Geodatabase the ``hazards`` stage reads for 2050 water stress (layer
``future_annual``) also carries ``baseline_annual`` with ``drr_cat``, WRI's drought-risk
category 0-4 inherited unchanged from Aqueduct 3.0 (no future-scenario drought exists in
Aqueduct 4.0, confirmed in the data dictionary). ``-9999`` marks "No Data" on about a quarter
of the sub-basins and becomes NaN here, never 0 (invariant 3).

Output: GeoDataFrame ``drr_cat`` (float, 0-4 or NaN) + geometry, one row per sub-basin.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from ..config import Settings
from ..rawfiles import resolve_vector
from ..registry import Source

NODATA = -9999


def prepare(gdf: gpd.GeoDataFrame, field: str = "drr_cat") -> gpd.GeoDataFrame:
    """Pure: keep the category and geometry, turn the -9999 sentinel into NaN."""
    if field not in gdf.columns:
        raise KeyError(f"Aqueduct baseline layer has no {field!r} column; got {list(gdf.columns)[:20]}")
    cat = pd.to_numeric(gdf[field], errors="coerce").astype("float64")
    cat = cat.where(cat != NODATA, np.nan)
    out = gpd.GeoDataFrame({field: cat.to_numpy()}, geometry=gdf.geometry.values, crs=gdf.crs)
    return out[out.geometry.notna() & ~out.geometry.is_empty].reset_index(drop=True)


def load(settings: Settings, source: Source, sources: dict[str, Source]) -> gpd.GeoDataFrame:
    layer = str(source.extra.get("baseline_layer") or "baseline_annual")
    path = resolve_vector(settings, source)
    gdf = gpd.read_file(path, layer=layer, columns=["drr_cat"])
    out = prepare(gdf)
    n_ok = int(out["drr_cat"].notna().sum())
    print(f"prep   {source.id}: {len(out)} sub-basins in {layer}, drr_cat present on {n_ok} ({100 * n_ok / max(1, len(out)):.0f}%)")
    return out
