"""World Bank price levels -> national tables (SPEC §20.6 ``cost``, global joiners).

``wb_icp_pli`` (``load_household``): the ICP 2021 household-consumption price level index
(World = 100) from the World Bank API as JSON: source 90, series 9100000, classification
``PX.WL``, every country and year. The ``all`` country selector returns 1,449 records on one
page (checked first-hand 2026-09-22). A record looks like::

    {"variable": [{"concept": "Country", "id": "FRA", "value": "France"},
                  {"concept": "Time", "id": "YR2021", "value": "2021"},
                  {"concept": "Series", "id": "9100000", ...},
                  {"concept": "Classification", "id": "PX.WL", ...}],
     "value": 110.2}                      # null when the country has no value that year

We keep the latest year with a value per country -> ``iso_a3, iso_a2, pli_household, year``.

``wb_gdp_pli`` (``load_gdp``): the WDI series PA.NUS.PPPC.RF, "price level ratio of the PPP
conversion factor (GDP) to the market exchange rate", as the fallback where ICP has no row.
It is a *ratio with the United States = 1*, not a World = 100 index, so it cannot share a
percentile pool with the ICP values as-is. It is rescaled onto the ICP world base through the
countries both cover (the median of ``pli_household / ratio``) -> ``iso_a3, iso_a2, pli_gdp,
year``; the joiner order in dimensions.yaml means it only ever fills the gaps. The zip holds
the data CSV (a few preamble lines before the ``Country Name,...`` header, a trailing comma on
every row) and ``Metadata_Country_*.csv``, whose blank ``Region`` marks the aggregates (World,
income groups, regions) that are dropped.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

from ..config import Settings
from ..registry import Source
from .util import find_column, iso3_to_iso2

ICP_SOURCE = "wb_icp_pli"  # the household table load_gdp calibrates against (also_needs)


# ---- ICP household consumption price level -----------------------------------------------


def parse_icp(payload: dict) -> pd.DataFrame:
    """``iso_a3, year, value`` from the API's JSON. A null ``value`` becomes NaN, never 0."""
    if isinstance(payload, list):
        # the API answers errors with a one-element list carrying a message
        raise ValueError(f"ICP API returned an error instead of data: {payload[:1]} (check the URL in sources.yaml)")
    source = payload.get("source") or {}
    data = source.get("data")
    if data is None:
        raise ValueError("ICP JSON has no source.data list; the API response shape may have changed (SPEC §15)")
    if int(payload.get("pages", 1) or 1) > 1:
        raise ValueError(f"ICP JSON is paginated ({payload.get('pages')} pages); raise per_page in the source url so one request returns everything")
    rows = []
    for rec in data:
        concepts = {v.get("concept"): v.get("id") for v in rec.get("variable", [])}
        year = re.sub(r"\D", "", str(concepts.get("Time") or ""))  # "YR2021" -> "2021"
        rows.append({"iso_a3": concepts.get("Country"), "year": int(year) if year else None, "value": rec.get("value")})
    df = pd.DataFrame(rows, columns=["iso_a3", "year", "value"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def prepare_household(df: pd.DataFrame, this_year: int | None = None) -> pd.DataFrame:
    """Pure part (unit-tested): latest year with a value per country, mapped to ISO2.

    Aggregates (regions, income groups) have no ISO2 code and drop out, as in the ILOSTAT loader.
    """
    this_year = this_year or dt.date.today().year
    df = df.dropna(subset=["iso_a3", "year", "value"]).copy()
    df = df[df["year"] <= this_year]
    df = df.sort_values("year").drop_duplicates("iso_a3", keep="last")
    iso3 = df["iso_a3"].astype(str)
    out = pd.DataFrame({"iso_a3": iso3, "iso_a2": iso3_to_iso2(iso3), "pli_household": df["value"].astype(float), "year": df["year"].astype(int)})
    return out.dropna(subset=["iso_a2"]).reset_index(drop=True)


def _read_icp_json(path: Path) -> pd.DataFrame:
    return prepare_household(parse_icp(json.loads(path.read_text(encoding="utf-8"))))


def load_household(settings: Settings, source: Source, sources: dict[str, Source]) -> pd.DataFrame:
    out = _read_icp_json(settings.raw(source.id) / source.files[0])
    print(f"prep   {source.id}: {len(out)} countries with an ICP household price level, latest year {out['year'].max() if len(out) else '-'}")
    return out


# ---- WDI GDP price level ratio, rescaled to the ICP world base ----------------------------


def read_wdi_zip(archive: Path) -> tuple[pd.DataFrame, set[str]]:
    """The WDI data CSV (as strings, header found by name so the preamble length does not
    matter) and the set of country codes that are real countries (non-blank ``Region`` in the
    country metadata; aggregates such as ``EAS`` or ``WLD`` have a blank one)."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        data = [n for n in names if n.startswith("API_") and n.lower().endswith(".csv")]
        meta = [n for n in names if n.startswith("Metadata_Country") and n.lower().endswith(".csv")]
        if len(data) != 1 or len(meta) != 1:
            raise FileNotFoundError(f"{archive.name}: expected one API_*.csv and one Metadata_Country_*.csv inside, found {names}")
        with z.open(data[0]) as fh:
            lines = fh.read().decode("utf-8-sig", errors="replace").splitlines()
        with z.open(meta[0]) as fh:
            countries_df = pd.read_csv(fh, dtype=str, keep_default_na=False)
    start = next((i for i, ln in enumerate(lines) if ln.lstrip('"').startswith("Country Name")), None)
    if start is None:
        raise ValueError(f"{archive.name}: no 'Country Name' header line in {data[0]}; the WDI CSV layout may have changed")
    ratios = pd.read_csv(io.StringIO("\n".join(lines[start:])), dtype=str, keep_default_na=False)
    ratios.columns = [str(c).strip() for c in ratios.columns]
    ratios = ratios.loc[:, [c for c in ratios.columns if not c.startswith("Unnamed")]]  # the trailing comma
    countries_df.columns = [str(c).strip() for c in countries_df.columns]
    region = countries_df[find_column(countries_df.columns, "Region")].astype(str).str.strip()
    code = countries_df[find_column(countries_df.columns, "Country Code")].astype(str).str.strip()
    return ratios, set(code[region != ""])


def prepare_gdp(ratios: pd.DataFrame, countries: set[str], household: pd.DataFrame, this_year: int | None = None) -> pd.DataFrame:
    """Pure part (unit-tested): latest ratio per real country, rescaled onto the ICP world base.

    ``pli_gdp = k * ratio`` with ``k`` the median of ``pli_household / ratio`` over the countries
    present in both tables. With the US = 1 in the ratio and the world = 100 in ICP, ``k`` lands
    near the ICP price level of the United States. Refuses (plain English) when nothing
    overlaps, because then the numbers could not be compared with the ICP values at all.
    """
    this_year = this_year or dt.date.today().year
    code_col = find_column(ratios.columns, "Country Code")
    years = sorted(c for c in ratios.columns if re.fullmatch(r"\d{4}", str(c)) and int(c) <= this_year)
    if not years:
        raise KeyError(f"WDI table has no year columns up to {this_year}; columns: {list(ratios.columns)[:10]}")
    codes = ratios[code_col].astype(str).str.strip()
    df = ratios[codes.isin(countries)]
    values = df[years].apply(pd.to_numeric, errors="coerce")  # "" (blank) -> NaN, never 0
    values.insert(0, "iso_a3", codes[codes.isin(countries)].to_numpy())
    long = values.melt(id_vars="iso_a3", var_name="year", value_name="ratio").dropna(subset=["ratio"])
    long["year"] = long["year"].astype(int)
    long = long[long["ratio"] > 0].sort_values("year").drop_duplicates("iso_a3", keep="last")
    overlap = long.merge(household[["iso_a3", "pli_household"]], on="iso_a3", how="inner")
    if overlap.empty:
        raise RuntimeError(
            "WDI price-level fallback: no country appears in both the WDI ratios and the ICP household table, "
            "so the US = 1 ratio cannot be rescaled to the ICP world base (is wb_icp_pli downloaded and parsed?)"
        )
    k = float((overlap["pli_household"] / overlap["ratio"]).median())
    iso3 = long["iso_a3"].astype(str)
    out = pd.DataFrame(
        {
            "iso_a3": iso3,
            "iso_a2": iso3_to_iso2(iso3),
            "pli_gdp": k * long["ratio"].astype(float),
            "pli_ratio_us": long["ratio"].astype(float),  # the untouched WDI ratio, for the record
            "year": long["year"],
        }
    )
    out = out.dropna(subset=["iso_a2"]).reset_index(drop=True)
    print(f"prep   wb_gdp_pli: {len(out)} countries; ratio rescaled by {k:.1f} from {len(overlap)} countries shared with ICP")
    return out


def load_gdp(settings: Settings, source: Source, sources: dict[str, Source]) -> pd.DataFrame:
    """``wb_gdp_pli``: needs the ICP household table too (``also_needs`` in sources.yaml)."""
    ratios, countries = read_wdi_zip(settings.raw(source.id) / source.files[0])
    icp_src = sources[ICP_SOURCE]
    household = _read_icp_json(settings.raw(icp_src.id) / icp_src.files[0])
    return prepare_gdp(ratios, countries, household)
