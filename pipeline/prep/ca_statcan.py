"""Statistics Canada 2021 Census Profile for dissemination areas (SPEC §13.34, §15).

The comprehensive download (98-401-X2021006, 2.25 GB zip, ~26.6 GB of cp1252 CSV split into six
regional members) is long-format: one row per geography x characteristic. It is streamed from the
zip in chunks, keeping only dissemination-area rows of the characteristics used here (ids as
published; C1_COUNT_TOTAL holds counts and, for rates, the same value as C10_RATE_TOTAL):

- 1     Population, 2021                                        -> ``population``
- 2223  Population aged 15+ by labour force status (25% sample)  -> ``pop_15plus`` (weight)
- 2229  Employment rate (%)                                      -> ``emp_rate``
- 345   Prevalence of low income, LIM-AT (%)                     -> ``low_income_rate``
- 1465  Households by shelter-cost-to-income ratio (25% sample)  -> ``households`` (weight)
- 1467  ... spending 30% or more of income on shelter costs      -> ``shelter_burden`` = 1467 / 1465

The tenant-only 30%+ rate (1492) is not used: at DA level it is 0 in most small DAs where the
owner-plus-tenant rate is not, an artefact of randomly rounded counts (checked 2026-09-23).
Suppressed or unavailable values are blank with a symbol (x, .., ..., F) and stay missing.
Boundaries: the 2021 cartographic DA file (EPSG:3347), joined on DGUID.
"""

from __future__ import annotations

import zipfile

import geopandas as gpd
import pandas as pd

IDS = {"1": "population", "2223": "pop_15plus", "2229": "emp_rate", "345": "low_income_rate", "1465": "households", "1467": "burdened"}
DA_LEVEL = "Dissemination area"
# column positions: the header repeats SYMBOL six times, so read by position
POS_DGUID, POS_LEVEL, POS_ID, POS_C1 = 1, 3, 8, 11


def load_profile(path, chunksize: int = 2_000_000) -> pd.DataFrame:
    parts = []
    with zipfile.ZipFile(path) as zf:
        members = [m for m in zf.namelist() if "_CSV_data_" in m and m.lower().endswith(".csv")]
        if not members:
            raise FileNotFoundError(f"{path}: no *_CSV_data_*.csv member; the StatCan layout may have changed (SPEC §15)")
        for member in members:
            with zf.open(member) as fh:
                reader = pd.read_csv(fh, encoding="cp1252", usecols=[POS_DGUID, POS_LEVEL, POS_ID, POS_C1], dtype=str, keep_default_na=False, chunksize=chunksize)
                for chunk in reader:
                    chunk.columns = ["DGUID", "GEO_LEVEL", "CID", "VALUE"]
                    keep = (chunk["GEO_LEVEL"] == DA_LEVEL) & chunk["CID"].isin(IDS.keys())
                    parts.append(chunk.loc[keep, ["DGUID", "CID", "VALUE"]])
    long = pd.concat(parts, ignore_index=True)
    long["VALUE"] = pd.to_numeric(long["VALUE"], errors="coerce")  # blanks (x, .., ...) -> missing
    wide = long.pivot_table(index="DGUID", columns="CID", values="VALUE", aggfunc="first").rename(columns=IDS)
    wide = wide.reindex(columns=list(IDS.values()))
    households = wide["households"].where(wide["households"] > 0)
    wide["shelter_burden"] = (wide["burdened"] / households).clip(0, 1)
    out = wide.drop(columns=["burdened"]).reset_index()
    return out.sort_values("DGUID", kind="stable").reset_index(drop=True)


def load(settings, source, sources) -> gpd.GeoDataFrame:
    geo = sources[source.extra["geometry"]]
    shp = settings.raw(geo.id) / geo.files[0]
    polys = gpd.read_file(f"zip://{shp.as_posix()}!{geo.extra['member']}", columns=["DGUID"])
    polys["geometry"] = polys.geometry.make_valid()
    polys = polys.to_crs(4326)
    table = load_profile(settings.raw(source.id) / source.files[0])
    return gpd.GeoDataFrame(polys.merge(table, on="DGUID", how="left"), geometry="geometry", crs=4326)
