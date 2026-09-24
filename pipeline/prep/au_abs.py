"""Australian Bureau of Statistics 2021 Census GCP DataPack for SA2 (SPEC §13.34, §15).

Short-header CSVs, one per table, keyed on ``SA2_CODE_2021`` (read as text):

- G01 ``Tot_P_P`` (persons)                                   -> ``population`` (weight)
- G43 ``P_15_yrs_over_P`` and ``Percnt_Employment_to_populn_P`` -> ``pop_15plus``, ``emp_rate`` (0-1)
- G02 ``Median_rent_weekly`` / ``Median_tot_hhd_inc_weekly``    -> ``median_rent_weekly`` and
  ``rent_share_income`` (a ratio of medians over different universes; the GCP has no rent-stress
  table, labelled as such)

ABS publishes an unavailable value as 0 (airports, industrial SA2s, "no usual address" rows), so
0 in a median or a rate is missing, never a real 0. The migratory / offshore / no-usual-address
pseudo-SA2s (codes ending 97979799 or 99999499) have no location and are dropped. Boundaries:
ASGS Edition 3 SA2 2021 (GDA2020, EPSG:7844, within 2 m of WGS84), joined on SA2_CODE21.
"""

from __future__ import annotations

import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd

TABLE = "2021 Census GCP Statistical Area 2 for AUS/2021Census_{}_AUST_SA2.csv"
PSEUDO_SUFFIXES = ("97979799", "99999499")


def _table(zf: zipfile.ZipFile, name: str, cols: list[str]) -> pd.DataFrame:
    member = TABLE.format(name)
    if member not in zf.namelist():
        raise FileNotFoundError(f"ABS DataPack: {member} not found; the layout may have changed (SPEC §15)")
    with zf.open(member) as fh:
        df = pd.read_csv(fh, dtype={"SA2_CODE_2021": str}, usecols=["SA2_CODE_2021", *cols])
    return df.set_index("SA2_CODE_2021")


def _zero_missing(s: pd.Series) -> pd.Series:
    v = pd.to_numeric(s, errors="coerce").astype("float64")
    return v.where(v > 0, np.nan)


def load_datapack(path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        g01 = _table(zf, "G01", ["Tot_P_P"])
        g02 = _table(zf, "G02", ["Median_rent_weekly", "Median_tot_hhd_inc_weekly"])
        g43 = _table(zf, "G43", ["P_15_yrs_over_P", "Percnt_Employment_to_populn_P"])
    df = g01.join(g02, how="outer").join(g43, how="outer")
    df = df[~df.index.str.endswith(PSEUDO_SUFFIXES)]
    rent = _zero_missing(df["Median_rent_weekly"])
    income = _zero_missing(df["Median_tot_hhd_inc_weekly"])
    out = pd.DataFrame(
        {
            "population": _zero_missing(df["Tot_P_P"]),
            "pop_15plus": _zero_missing(df["P_15_yrs_over_P"]),
            "emp_rate": _zero_missing(df["Percnt_Employment_to_populn_P"]) / 100.0,
            "median_rent_weekly": rent,
            "rent_share_income": rent / income,
        },
        index=df.index,
    )
    return out.rename_axis("SA2_CODE_2021").reset_index()


def load(settings, source, sources) -> gpd.GeoDataFrame:
    geo = sources[source.extra["geometry"]]
    shp = settings.raw(geo.id) / geo.files[0]
    polys = gpd.read_file(f"zip://{shp.as_posix()}!{geo.extra['member']}", columns=["SA2_CODE21"])
    polys = polys[polys.geometry.notna()].set_crs(7844, allow_override=True).to_crs(4326)
    table = load_datapack(settings.raw(source.id) / source.files[0])
    out = polys.rename(columns={"SA2_CODE21": "SA2_CODE_2021"}).merge(table, on="SA2_CODE_2021", how="left")
    return gpd.GeoDataFrame(out, geometry="geometry", crs=4326)
