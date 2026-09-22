"""MIT Election Lab county presidential returns -> county polygons with the 2024 two-party
margin (SPEC §20.6 pol, kind signed).

CSV columns: ``state, county_name, year, state_po, county_fips (not zero-padded), office,
candidate, party, candidatevotes, totalvotes, version, mode``. Some states report per voting
mode plus a ``TOTAL`` row, others only per mode, so per county we keep the TOTAL rows when any
exist and otherwise sum every mode. ``margin_2024 = 100 * (D - R) / (D + R)``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source

YEAR = 2024
OFFICE = "US PRESIDENT"


def prepare(df: pd.DataFrame, year: int = YEAR) -> pd.DataFrame:
    """Pure part (unit-tested): county GEOID -> margin and shares."""
    df = df[(pd.to_numeric(df["year"], errors="coerce") == year) & (df["office"].astype(str).str.upper() == OFFICE)].copy()
    df = df.dropna(subset=["county_fips"])
    df["GEOID"] = df["county_fips"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    df["mode"] = df["mode"].astype(str).str.upper()
    df["candidatevotes"] = pd.to_numeric(df["candidatevotes"], errors="coerce").fillna(0)
    has_total = df.groupby("GEOID")["mode"].transform(lambda m: (m == "TOTAL").any())
    df = df[(~has_total) | (df["mode"] == "TOTAL")]
    party = df["party"].astype(str).str.upper()
    dem = df[party == "DEMOCRAT"].groupby("GEOID")["candidatevotes"].sum()
    rep = df[party == "REPUBLICAN"].groupby("GEOID")["candidatevotes"].sum()
    total = df.groupby("GEOID")["candidatevotes"].sum()
    out = pd.DataFrame({"dem": dem, "rep": rep, "totalvotes": total}).fillna({"dem": 0, "rep": 0})
    two = out["dem"] + out["rep"]
    with np.errstate(divide="ignore", invalid="ignore"):
        out["margin_2024"] = (100.0 * (out["dem"] - out["rep"]) / two).where(two > 0)
        out["dem_share"] = (100.0 * out["dem"] / two).where(two > 0)
        out["rep_share"] = (100.0 * out["rep"] / two).where(two > 0)
    out = out.dropna(subset=["margin_2024"]).reset_index()
    return out[["GEOID", "margin_2024", "dem_share", "rep_share", "totalvotes"]]


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    df = pd.read_csv(settings.raw(source.id) / source.files[0], dtype={"county_fips": str}, low_memory=False)
    table = prepare(df)
    counties = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOID"]).to_crs(4326)
    merged = counties.merge(table, on="GEOID", how="inner")
    print(f"prep   medsl_county_pres: {len(merged)} counties with a 2024 margin (of {len(table)} in the returns, {len(counties)} polygons)")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
