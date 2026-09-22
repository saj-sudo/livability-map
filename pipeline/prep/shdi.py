"""Global Data Lab Subnational HDI -> region polygons with the latest ``shdi`` (SPEC §7, §15.4).

Two manual downloads (registration-gated): the SHDI CSV (``gdl_shdi``) and the GDL region
shapefile zip (``gdl_shdi_regions``). Column names differ slightly between versions, so the code,
level, year and value columns are located case-insensitively. Output: ``GDLCODE, shdi, year,
geometry`` (the joiner uses ``polygon_centroid`` on ``shdi``).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column

CSV_SOURCE = "gdl_shdi"


def load(settings: Settings, source: Source, sources: dict[str, Source]) -> gpd.GeoDataFrame:
    csv_src = sources[CSV_SOURCE]
    csv_path = settings.raw(csv_src.id) / csv_src.files[0]
    table = pd.read_csv(csv_path, low_memory=False)
    code_col = find_column(table.columns, "GDLCODE", "GDLcode", "gdlcode")
    value_col = find_column(table.columns, "shdi", "SHDI")
    year_col = find_column(table.columns, "year")
    if "level" in {c.lower() for c in table.columns}:
        level_col = find_column(table.columns, "level")
        table = table[table[level_col].astype(str).str.lower().str.startswith("subnat")]
    table = table[[code_col, year_col, value_col]].rename(columns={code_col: "GDLCODE", year_col: "year", value_col: "shdi"})
    table["shdi"] = pd.to_numeric(table["shdi"], errors="coerce")
    table = table.dropna(subset=["shdi"]).sort_values("year").drop_duplicates("GDLCODE", keep="last")

    regions = gpd.read_file(rawfiles.resolve_vector(settings, source))
    rcode = find_column(regions.columns, "GDLCODE", "GDLcode", "gdlcode")
    regions = regions[[rcode, "geometry"]].rename(columns={rcode: "GDLCODE"})
    if regions.crs is None:
        regions = regions.set_crs(4326)
    elif regions.crs.to_epsg() != 4326:
        regions = regions.to_crs(4326)
    merged = regions.merge(table, on="GDLCODE", how="inner")
    print(f"prep   gdl_shdi_regions: {len(merged)} regions with SHDI out of {len(regions)} polygons / {len(table)} table rows")
    return gpd.GeoDataFrame(merged[["GDLCODE", "shdi", "year", "geometry"]], geometry="geometry", crs=4326)
