"""HUD Fair Market Rents -> county polygons with the 2-bedroom rent (SPEC §20.6 ``rent``, US
joiner). USD per month, FY2026.

``FY26_FMRs.xlsx`` (public domain, one sheet) has one row per FMR area: ``fips`` (10 digits:
the 5-digit county FIPS followed by ``99999`` for a whole county, or a town code in the six
New England states where FMRs are set per town), ``state``, ``county``, ``countyname``,
``metro``, ``fmr_0 .. fmr_4`` (0 to 4 bedrooms). Older files call the columns ``fips2010`` /
``fmr2``; ``find_column`` accepts both. Per county we keep the whole-county row when there is
one and otherwise the median of its town rows; a county whose rent is blank stays missing
rather than 0 (invariant 3). Joined to the Census county polygons (``cb_counties``) on GEOID.
"""

from __future__ import annotations

import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column, read_xlsx

WHOLE_COUNTY = "99999"  # sub-county part of the 10-digit fips when the FMR applies county-wide


def prepare(fmr: pd.DataFrame) -> pd.DataFrame:
    """Pure part (unit-tested): ``GEOID, fmr_2br`` with one row per county."""
    fips_col = find_column(fmr.columns, "fips")  # exact "fips", else "fips2010" / "fips2020" ...
    rent_col = find_column(fmr.columns, "fmr_2", "fmr2")
    # Excel drops leading zeros and may hand us floats ("100199999.0"); restore the 10 digits
    fips = fmr[fips_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip().str.zfill(10)
    df = pd.DataFrame(
        {
            "GEOID": fips.str[:5],
            "whole": fips.str[5:] == WHOLE_COUNTY,
            "fmr_2br": pd.to_numeric(fmr[rent_col], errors="coerce"),  # "(NA)" and blanks -> NaN
        }
    ).dropna(subset=["fmr_2br"])
    towns = df[~df["whole"]].groupby("GEOID")["fmr_2br"].median()
    whole = df[df["whole"]].drop_duplicates("GEOID").set_index("GEOID")["fmr_2br"]
    values = towns.to_dict()
    values.update(whole.to_dict())  # a whole-county row wins over the town median
    out = pd.DataFrame({"GEOID": list(values), "fmr_2br": [float(v) for v in values.values()]})
    return out.sort_values("GEOID").reset_index(drop=True)


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    path = settings.raw(source.id) / source.files[0]
    table = prepare(read_xlsx(path, source.extra.get("sheet", 0), int(source.extra.get("header_row", 1))))
    counties = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOID"]).to_crs(4326)
    counties["GEOID"] = counties["GEOID"].astype(str).str.strip()
    merged = counties.merge(table, on="GEOID", how="inner")
    share = len(merged) / max(1, len(table))
    print(f"prep   {source.id}: {len(merged)} counties with a 2-bedroom FMR ({100 * share:.0f}% of {len(table)} HUD counties matched, {len(counties)} polygons)")
    if share < 0.9:
        unmatched = sorted(set(table["GEOID"]) - set(counties["GEOID"]))[:10]
        raise RuntimeError(f"{source.id}: only {100 * share:.0f}% of HUD counties found a polygon; first unmatched GEOIDs: {unmatched}. Check the fips column and the Census county vintage")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
