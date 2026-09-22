"""World Bank Global Subnational Atlas of Poverty -> admin1 polygons with the share of people
above the $4.20/day (2021 PPP) line (SPEC §20.6 incmix, global joiner).

Inputs: ``wb_gsap`` (xlsx, sheet "Data 2023": ``code, geo_code, poor300_ln, poor420_ln, ...``)
and ``wb_gsap_regions`` (zip with ``GSAP_AM25_2023.gpkg`` keyed by ``geo_code``). Output:
``geo_code, poor420_ln, nonpoor_share, geometry``; ``nonpoor_share = 1 - poor420_ln`` so higher
is better like the US income-mix construct it sits beside (different constructs, labeled).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column, read_xlsx

REGIONS_SOURCE = "wb_gsap_regions"
LINE = "poor420_ln"


def load(settings: Settings, source: Source, sources: dict[str, Source]) -> gpd.GeoDataFrame:
    path = settings.raw(source.id) / source.files[0]
    table = read_xlsx(path, source.extra.get("sheet", "Data 2023"), int(source.extra.get("header_row", 1)))
    code_col = find_column(table.columns, "geo_code")
    line_col = find_column(table.columns, LINE)
    table = table[[code_col, line_col]].rename(columns={code_col: "geo_code", line_col: LINE})
    table[LINE] = pd.to_numeric(table[LINE], errors="coerce")
    table = table.dropna(subset=[LINE]).drop_duplicates("geo_code")
    table["nonpoor_share"] = (1.0 - table[LINE]).clip(0.0, 1.0)

    regions = gpd.read_file(rawfiles.resolve_vector(settings, sources[REGIONS_SOURCE]))
    rcode = find_column(regions.columns, "geo_code")
    regions = regions[[rcode, "geometry"]].rename(columns={rcode: "geo_code"})
    if regions.crs is None:
        regions = regions.set_crs(4326)
    elif regions.crs.to_epsg() != 4326:
        regions = regions.to_crs(4326)
    merged = regions.merge(table, on="geo_code", how="inner")
    share = len(merged) / max(1, len(table))
    print(f"prep   wb_gsap: {len(merged)} regions matched ({100 * share:.0f}% of {len(table)} table rows, {len(regions)} polygons)")
    if share < 0.9:
        unmatched = sorted(set(table["geo_code"]) - set(regions["geo_code"]))[:10]
        raise RuntimeError(f"GSAP: only {100 * share:.0f}% of table rows found a polygon; first unmatched geo_codes: {unmatched}")
    return gpd.GeoDataFrame(merged[["geo_code", LINE, "nonpoor_share", "geometry"]], geometry="geometry", crs=4326)
