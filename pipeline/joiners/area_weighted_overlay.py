"""``area_weighted_overlay``: small polygons (tracts, block groups, districts) -> hex.

value(hex) = sum_i(w_i * v_i) / sum_i(w_i) over polygons i overlapping the hex, where
w_i = overlap_area_i * density_i and density_i = weight_field_i / polygon_area_i (population
density when ``weight_field`` is a population count). Without ``weight_field`` it is a plain
area-weighted mean. Areas are computed in an equal-area CRS (EPSG:6933).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import h3util

EQUAL_AREA = 6933


def area_weighted_overlay(
    hexes: pd.DataFrame,
    polygons: gpd.GeoDataFrame,
    field: str,
    weight_field: str | None = None,
    min_coverage: float = 0.05,
) -> pd.Series:
    """``min_coverage``: hexes with less than this fraction of their area covered by polygons
    with a value get NaN rather than a value from a sliver."""
    if field not in polygons.columns:
        raise KeyError(f"polygon layer has no field {field!r}")
    polys = polygons[[c for c in {field, weight_field, "geometry"} if c]].copy()
    if polys.crs is None:
        polys = polys.set_crs(4326)
    polys = polys.to_crs(EQUAL_AREA)
    polys = polys[polys[field].notna()]
    polys["_parea"] = polys.geometry.area
    if weight_field:
        polys["_dens"] = polys[weight_field].fillna(0).astype("float64") / polys["_parea"].replace(0, np.nan)
    else:
        polys["_dens"] = 1.0
    polys["_dens"] = polys["_dens"].fillna(0)

    hexgdf = gpd.GeoDataFrame(
        {"_i": np.arange(len(hexes))},
        geometry=h3util.cell_polygons(hexes["h3"]),
        crs=4326,
    ).to_crs(EQUAL_AREA)
    hexgdf["_harea"] = hexgdf.geometry.area

    inter = gpd.overlay(hexgdf, polys, how="intersection", keep_geom_type=False)
    if inter.empty:
        return pd.Series(np.nan, index=hexes.index, name=field)
    inter["_oa"] = inter.geometry.area
    inter["_w"] = inter["_oa"] * inter["_dens"]
    inter["_wv"] = inter["_w"] * inter[field].astype("float64")
    g = inter.groupby("_i").agg(_w=("_w", "sum"), _wv=("_wv", "sum"), _oa=("_oa", "sum"), _harea=("_harea", "first"))
    covered = g["_oa"] / g["_harea"]
    with np.errstate(divide="ignore", invalid="ignore"):
        val = g["_wv"] / g["_w"]
    val = val.where((covered >= min_coverage) & (g["_w"] > 0))
    out = pd.Series(np.nan, index=range(len(hexes)), dtype="float64")
    out.loc[val.index] = val.to_numpy()
    out.index = hexes.index
    out.name = field
    return out
