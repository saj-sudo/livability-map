"""English Indices of Deprivation 2025, File 7, joined to ONS LSOA 2021 boundaries (SPEC §20.6, §15).

File 7 has one row per 2021 LSOA in England (33,755); the ONS BGC boundaries cover England and
Wales (35,672, EPSG:27700). The join is on ``LSOA21CD``; Welsh LSOAs keep missing scores because
the IoD is England only (Wales has its own index, not used here). Output columns:
``LSOA21CD, LSOA21NM, imd_score, income_dep_rate, emp_dep_rate, health_dep, housing_barriers,
population, pop_working`` plus the WGS84 geometry. The ``area_weighted_overlay`` joiner weights
the rates by population (``pop_working`` for the employment rate).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

# our column -> File 7 header (exact strings, SPEC §15 2026-09-22)
COLUMNS = {
    "LSOA21CD": "LSOA code (2021)",
    "imd_score": "Index of Multiple Deprivation (IMD) Score",
    "income_dep_rate": "Income Score (rate)",
    "emp_dep_rate": "Employment Score (rate)",
    "health_dep": "Health Deprivation and Disability Score",
    "housing_barriers": "Barriers to Housing and Services Score",
    "population": "Total population: mid 2022",
    "pop_working": "Working age population 18-66 (for use with Employment Deprivation Domain): mid 2022",
}
NUMERIC = [c for c in COLUMNS if c != "LSOA21CD"]


def load_frames(csv_path, geo_path) -> gpd.GeoDataFrame:
    header = pd.read_csv(csv_path, nrows=0, encoding="utf-8-sig").columns
    missing = [h for h in COLUMNS.values() if h not in header]
    if missing:
        raise KeyError(f"IoD2025 File 7 column(s) {missing} not found; the published headers may have changed (SPEC §15)")
    scores = pd.read_csv(csv_path, usecols=list(COLUMNS.values()), encoding="utf-8-sig").rename(columns={v: k for k, v in COLUMNS.items()})
    lsoa = gpd.read_file(geo_path)
    lsoa = lsoa[["LSOA21CD", "LSOA21NM", "geometry"]]
    lsoa = lsoa.to_crs(4326) if lsoa.crs is not None else lsoa.set_crs(4326)
    out = lsoa.merge(scores, on="LSOA21CD", how="left")  # Welsh LSOAs stay missing: IoD is England only
    for c in NUMERIC:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return gpd.GeoDataFrame(out, geometry="geometry", crs=4326)


def load(settings, source, sources) -> gpd.GeoDataFrame:
    geo = sources[source.extra["geometry"]]
    return load_frames(settings.raw(source.id) / source.files[0], settings.raw(geo.id) / geo.files[0])
