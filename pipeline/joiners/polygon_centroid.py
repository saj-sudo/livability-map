"""``polygon_centroid``: value of the polygon containing each hex centroid."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def polygon_centroid(hexes: pd.DataFrame, polygons: gpd.GeoDataFrame, field: str) -> pd.Series:
    if field not in polygons.columns:
        raise KeyError(f"polygon layer has no field {field!r}; columns: {list(polygons.columns)}")
    pts = gpd.GeoDataFrame(
        {"_i": range(len(hexes))},
        geometry=gpd.points_from_xy(hexes["lng"], hexes["lat"]),
        crs=4326,
    )
    polys = polygons[[field, "geometry"]]
    if polys.crs is None:
        polys = polys.set_crs(4326)
    elif polys.crs.to_epsg() != 4326:
        polys = polys.to_crs(4326)
    joined = gpd.sjoin(pts, polys, how="left", predicate="within")
    # a centroid exactly on a shared boundary can match twice; keep the first
    joined = joined[~joined.index.duplicated(keep="first")]
    out = joined[field].reindex(range(len(hexes)))
    out.index = hexes.index
    out.name = field
    return out
