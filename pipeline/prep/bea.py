"""BEA Regional Price Parities -> state or metro polygons with the all-items RPP (SPEC §20.6
``cost``, US joiners). The index is relative to the national average: US = 100.

Two zips from https://apps.bea.gov/regional/zip/ (checked first-hand 2026-09-22):
``SARPP.zip`` (states, member ``SARPP_STATE_2008_2024.csv``) and ``MARPP.zip`` (metropolitan
statistical areas, member ``MARPP_MSA_2008_2024.csv``). Both share the header
``GeoFIPS,GeoName,Region,TableName,LineCode,IndustryClassification,Description,Unit,2008..2024``
and end with four footer lines (a note, a legend, ``(NA)``, the update date). ``GeoFIPS`` is
quoted and space-padded: ``" 01000"`` is state FIPS ``01`` followed by ``000``; in the metro
table it is the 5-digit CBSA code. LineCode 1 is "RPPs: All items"; ``(NA)`` marks a missing
value. There is no county table, so the ``cost`` dimension falls back from metro to state.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column

ALL_ITEMS_LINE = "1"  # LineCode of "RPPs: All items" (2 = goods, 3 = rents, 4 = other services)


def read_zip_member(archive: Path, member: str | None = None) -> pd.DataFrame:
    """The BEA CSV inside the zip as strings, with the footer lines removed.

    The footer lines have fewer fields than the header, so pandas pads them with blanks; any row
    whose ``GeoFIPS`` is not a number (notes, the legend, the update date) is dropped afterwards.
    Rows with *more* fields than the header (none today) are skipped rather than failing.
    """
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if member is None:
            csvs = [n for n in names if n.lower().endswith(".csv")]
            if len(csvs) != 1:
                raise FileNotFoundError(f"{archive.name}: expected exactly one CSV inside, found {csvs}; set `member:` on the source in sources.yaml")
            member = csvs[0]
        if member not in names:
            raise FileNotFoundError(f"{archive.name} has no member {member!r}; members: {names[:10]}")
        with z.open(member) as fh:
            text = fh.read().decode("utf-8-sig", errors="replace")
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, on_bad_lines="skip")
    df.columns = [str(c).strip() for c in df.columns]
    fips_col = find_column(df.columns, "GeoFIPS")
    fips = df[fips_col].astype(str).str.replace('"', "").str.strip()
    return df[fips.str.fullmatch(r"\d+")].reset_index(drop=True)


def _year_columns(columns) -> list[str]:
    """The four-digit year columns, oldest first."""
    return sorted(c for c in columns if re.fullmatch(r"\d{4}", str(c)))


def prepare(df: pd.DataFrame, level: str) -> pd.DataFrame:
    """Pure part (unit-tested): ``GEOID, rpp_all, year`` for the all-items line, latest year.

    ``level`` is ``state`` (GEOID = 2-digit state FIPS taken from the ``SS000`` GeoFIPS) or
    ``metro`` (GEOID = the 5-digit CBSA code as-is). Rows whose GeoFIPS starts with ``00`` are
    national aggregates (the United States and its metropolitan / non-metropolitan portions);
    they have no polygon and are dropped. ``(NA)`` becomes NaN and the row is dropped, so a
    missing parity is never written as 0 (invariant 3).
    """
    if level not in ("state", "metro"):
        raise ValueError(f"level must be 'state' or 'metro', not {level!r}")
    years = _year_columns(df.columns)
    if not years:
        raise KeyError(f"BEA table has no year columns; columns: {list(df.columns)[:12]}")
    latest = years[-1]
    line = df[find_column(df.columns, "LineCode")].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    fips = df[find_column(df.columns, "GeoFIPS")].astype(str).str.replace('"', "").str.strip()
    keep = (line == ALL_ITEMS_LINE) & fips.str.fullmatch(r"\d{5}") & ~fips.str.startswith("00")
    if level == "state":
        keep &= fips.str.endswith("000")  # SS000: a state; anything else in this table is not
        geoid = fips.str[:2]
    else:
        geoid = fips
    out = pd.DataFrame(
        {
            "GEOID": geoid[keep].to_numpy(),
            "rpp_all": pd.to_numeric(df.loc[keep, latest], errors="coerce").to_numpy(),
            "year": int(latest),
        }
    )
    return out.dropna(subset=["rpp_all"]).drop_duplicates("GEOID").reset_index(drop=True)


def _load(settings: Settings, source: Source, sources: dict[str, Source], level: str, key_note: str):
    """Shared loader: parse the zip, join the table to the Census polygons named by ``geometry``."""
    import geopandas as gpd

    archive = settings.raw(source.id) / source.files[0]
    table = prepare(read_zip_member(archive, source.extra.get("member")), level=level)
    polygons = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOID"]).to_crs(4326)
    polygons["GEOID"] = polygons["GEOID"].astype(str).str.strip()
    merged = polygons.merge(table, on="GEOID", how="inner")
    share = len(merged) / max(1, len(table))
    year = int(table["year"].iloc[0]) if len(table) else "-"
    print(f"prep   {source.id}: {len(merged)} {level} polygons with an all-items RPP for {year} ({100 * share:.0f}% of {len(table)} BEA rows matched on {key_note})")
    if share < 0.9:
        unmatched = sorted(set(table["GEOID"]) - set(polygons["GEOID"]))[:10]
        raise RuntimeError(
            f"{source.id}: only {100 * share:.0f}% of BEA rows found a polygon; first unmatched GEOIDs: {unmatched}. "
            "The Census cartographic vintage may not match the BEA table (check sources.yaml)."
        )
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)


def load_state(settings: Settings, source: Source, sources: dict[str, Source]):
    """``bea_rpp_state``: SARPP.zip -> state polygons (``cb_states``) with ``rpp_all``."""
    return _load(settings, source, sources, "state", "the 2-digit state FIPS")


def load_metro(settings: Settings, source: Source, sources: dict[str, Source]):
    """``bea_rpp_metro``: MARPP.zip -> CBSA polygons (``cb_cbsa``) with ``rpp_all``. The Census
    file also carries micropolitan areas, which BEA does not price; they simply do not match."""
    return _load(settings, source, sources, "metro", "the 5-digit CBSA code")
