"""``point_density``: count of points per hex, optionally per 10,000 residents."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .. import h3util


def point_density(hexes: pd.DataFrame, points: gpd.GeoDataFrame, res: int, per_capita: bool = False, per: int = 10_000) -> pd.Series:
    pts = points
    if pts.crs is None:
        pts = pts.set_crs(4326)
    elif pts.crs.to_epsg() != 4326:
        pts = pts.to_crs(4326)
    pts = pts[pts.geometry.notna() & ~pts.geometry.is_empty]
    cells = h3util.latlng_to_cells(pts.geometry.y.to_numpy(), pts.geometry.x.to_numpy(), res)
    counts = pd.Series(cells).value_counts()
    out = hexes["h3"].map(counts).fillna(0).astype("float64")
    if per_capita:
        if "population" not in hexes.columns:
            raise KeyError("per_capita needs a population column (run `pop` first)")
        pop = hexes["population"].astype("float64")
        with np.errstate(divide="ignore", invalid="ignore"):
            out = (out / pop * per).where(pop > 0)
    out.index = hexes.index
    out.name = "point_density"
    return out
