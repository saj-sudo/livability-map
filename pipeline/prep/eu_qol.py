"""Eurostat / DG REGIO "Perception of quality of life in European cities" survey (2023 wave,
about 83 cities) -> GISCO Urban Audit city polygons carrying three agreement shares
(SPEC §13.48: `lgbtq` EU-city joiner, `immig`, `safe`).

Each item's value is the share of respondents who agree (strongly + somewhat) that the city is a
good place for gay or lesbian people, a good place for immigrants from other countries, or that
they feel safe walking alone at night in the city, as published (the base includes "don't know").

The survey table's layout and its item and city codes are from memory (source `verified: search`),
so this loader accepts the layouts a download plausibly has:

- Eurostat SDMX-CSV (``indic_ur``, ``cities``, ``TIME_PERIOD``, ``OBS_VALUE``), exported with
  labels so the items can be recognised by their wording;
- the Eurostat bulk TSV (first column ``indic_ur,cities\\time``, one column per year, values
  with flags such as ``45.2 u`` and ``:`` for missing);
- a generic long table: a city column, an item (question) column, an optional answer column and
  a value column.

Items are recognised by their wording (``ITEM_PATTERNS``) or by codes listed under ``items:`` on
the source in sources.yaml; answers by their wording (``strongly agree`` + ``somewhat agree``,
or a ready-made "agree (total)" row, which wins over its parts). Rows for other questions are
ignored. Only the latest year in the table is kept, so every value comes from one wave. Cities
match the boundaries on the URAU code (``DE001C``; a trailing digit is ignored), else on the
normalised city name. A city or an item the table does not have stays missing, never 0.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column, normalize_name

ITEMS = ("gay_good_pct", "immig_good_pct", "safe_night_pct")

# item column -> (must match, must not match) on the lowercased item text
ITEM_PATTERNS: dict[str, tuple[str, str | None]] = {
    "gay_good_pct": (r"\bgay|lesbian", None),
    "immig_good_pct": (r"immigrant|foreigners?\b|migrants?\b", r"\bgay|lesbian"),
    "safe_night_pct": (r"\bsafe.*\bnight|\bnight.*\bsafe", None),
}
_POSITIVE = re.compile(r"\b(?:strongly|totally|somewhat|rather|fairly|very)\s+(?:agree|safe)\b")
_NEGATIVE = re.compile(r"disagree|unsafe|not\s+(?:very\s+|at\s+all\s+)?safe|not\s+agree")
_TOTAL = re.compile(r"\btotal\b.*\bagree\b|\bagree\b.*\btotal\b")
_URAU = re.compile(r"^([A-Z]{2}\d{3}[A-Z])\d?$")

_CITY_COLS = ("urau_code", "city_code", "cities", "city", "geo", "urau", "city_name", "name")
_ITEM_COLS = ("indic_ur", "question", "item", "indicator", "variable", "description")
_ANSWER_COLS = ("answer", "response", "category", "level", "reply")
_VALUE_COLS = ("obs_value", "value", "percent", "percentage", "share", "pct")
_YEAR_COLS = ("time_period", "time", "year", "wave")


def _number(s: pd.Series) -> pd.Series:
    """Numbers out of published cells: "45.2 u" -> 45.2, ":" or "" -> NaN."""
    return pd.to_numeric(s.astype(str).str.extract(r"(-?\d+(?:[.,]\d+)?)", expand=False).str.replace(",", "."), errors="coerce")


def _maybe(columns, *candidates: str) -> str | None:
    try:
        return find_column(columns, *candidates)
    except KeyError:
        return None


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Any supported layout -> columns ``city``, ``text`` (item + answer wording), ``value``
    and ``year`` (NaN when the table has none)."""
    df = df.rename(columns=lambda c: str(c).strip().lstrip("﻿"))
    first = str(df.columns[0])
    if "\\" in first:  # Eurostat bulk TSV: "indic_ur,cities\time" then one column per year
        keys = first.split("\\")[0].split(",")
        split = df[first].astype(str).str.split(",", expand=True)
        split.columns = keys[: split.shape[1]]
        years = [c for c in df.columns[1:] if re.fullmatch(r"\d{4}", str(c).strip())]
        if not years:
            raise KeyError(f"EU QoL survey TSV: no year columns after {first!r}; columns found: {list(df.columns)[:30]}")
        wide = pd.concat([split, df[years]], axis=1)
        long = wide.melt(id_vars=list(split.columns), value_vars=years, var_name="year", value_name="value")
        item = find_column(split.columns, *_ITEM_COLS)
        city = find_column(split.columns, *_CITY_COLS)
        return pd.DataFrame({"city": long[city].astype(str).str.strip(), "text": long[item].astype(str), "value": _number(long["value"]), "year": pd.to_numeric(long["year"].astype(str).str.strip(), errors="coerce")})
    try:
        city = find_column(df.columns, *_CITY_COLS)
        item = find_column(df.columns, *_ITEM_COLS)
        value = find_column(df.columns, *_VALUE_COLS)
    except KeyError:
        raise KeyError(
            "EU QoL survey table: expected a city column (one of " + ", ".join(_CITY_COLS) + "), an item column (one of "
            + ", ".join(_ITEM_COLS) + ") and a value column (one of " + ", ".join(_VALUE_COLS) + "); columns found: " + repr(list(df.columns)[:30])
        ) from None
    answer = _maybe([c for c in df.columns if c not in (city, item, value)], *_ANSWER_COLS)
    year = _maybe([c for c in df.columns if c not in (city, item, value)], *_YEAR_COLS)
    text = df[item].astype(str) + (" | " + df[answer].astype(str) if answer else "")
    # a "Codes and labels" export may carry the label in a column next to the code ("indic_ur_label")
    label = next((c for c in df.columns if c != item and str(c).lower().startswith(str(item).lower()) and "label" in str(c).lower()), None)
    if label:
        text = text + " | " + df[label].astype(str)
    return pd.DataFrame({"city": df[city].astype(str).str.strip(), "text": text, "value": _number(df[value]), "year": pd.to_numeric(df[year], errors="coerce") if year else np.nan})


def classify(text: pd.Series, codes: dict[str, list[str]] | None = None) -> pd.Series:
    """Which of ``ITEMS`` a row belongs to (None for other questions): first by code (``items:``
    on the source), then by wording."""
    low = text.str.lower()
    out = pd.Series(None, index=text.index, dtype=object)
    for col, wanted in (codes or {}).items():
        if col not in ITEMS:
            raise KeyError(f"items: unknown item {col!r}; expected one of {ITEMS}")
        pat = "|".join(re.escape(str(c).lower()) for c in wanted or [])
        if pat:
            out[out.isna() & low.str.contains(rf"(?:^|[\s|:,])(?:{pat})(?:$|[\s|:,])", regex=True)] = col
    for col, (must, must_not) in ITEM_PATTERNS.items():
        hit = out.isna() & low.str.contains(must, regex=True)
        if must_not:
            hit &= ~low.str.contains(must_not, regex=True)
        out[hit] = col
    return out


def agreement(long: pd.DataFrame, codes: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Tidy rows -> one row per city with the agreement share (percent) of each item: the
    "agree (total)" row when the table has one, else strongly + somewhat agree. Other questions,
    disagreement and "don't know" rows are ignored; the latest year in the table is kept."""
    d = long.copy()
    d["item"] = classify(d["text"], codes)
    d = d[d["item"].notna() & d["value"].notna()]
    if d.empty:
        raise ValueError(
            "EU QoL survey table: no row matched the three items (good place for gay or lesbian people, for immigrants, "
            "feeling safe at night). Export the table with labels, or list the item codes under `items:` on the source. "
            f"Item texts seen: {sorted(long['text'].astype(str).unique())[:12]}"
        )
    if d["year"].notna().any():
        d = d[d["year"] == d["year"].max()]
    low = d["text"].str.lower()
    d = d.assign(total=low.str.contains(_TOTAL, regex=True) & ~low.str.contains(_NEGATIVE, regex=True), positive=low.str.contains(_POSITIVE, regex=True) & ~low.str.contains(_NEGATIVE, regex=True))
    totals = d[d["total"]].groupby(["city", "item"])["value"].max()
    parts = d[d["positive"] & ~d["total"]].groupby(["city", "item"])["value"].sum(min_count=1)
    share = totals.combine_first(parts)  # a published total wins over summing its parts
    if share.empty:
        raise ValueError(f"EU QoL survey table: the three items were found but no 'strongly / somewhat agree' answer rows; texts seen: {sorted(d['text'].unique())[:12]}")
    wide = share.unstack("item").reindex(columns=list(ITEMS))
    if float(np.nanmax(wide.to_numpy(dtype="float64"))) <= 1.0:  # published as fractions
        wide = wide * 100.0
    wide = wide.where((wide >= 0) & (wide <= 100.5))
    return wide.dropna(how="all").rename_axis(index="city", columns=None).reset_index()


def city_key(code: str) -> str | None:
    """URAU city code stem: "DE001C1" and "de001c" -> "DE001C"; None for anything else."""
    m = _URAU.match(str(code).strip().upper())
    return m.group(1) if m else None


def attach(shares: pd.DataFrame, cities):
    """Survey shares -> city polygons (GeoDataFrame with ``city_code``, ``city_name`` and the
    three items). Matches on the URAU code stem, else on the normalised name."""
    import geopandas as gpd

    code_col = find_column(cities.columns, "urau_code", "urau_id", "city_code", "id")
    name_col = _maybe(cities.columns, "urau_name", "city_name", "name")
    polys = gpd.GeoDataFrame({"city_code": cities[code_col].astype(str), "city_name": cities[name_col].astype(str) if name_col else cities[code_col].astype(str)}, geometry=cities.geometry, crs=cities.crs)
    polys["_key"] = polys["city_code"].map(city_key)
    polys["_name"] = polys["city_name"].map(normalize_name)
    s = shares.copy()
    s["_key"] = s["city"].map(city_key)
    by_code = s[s["_key"].notna()].drop_duplicates("_key")
    by_name = s[s["_key"].isna()].assign(_name=lambda x: x["city"].map(normalize_name)).drop_duplicates("_name")
    a = polys[polys["_key"].notna()].drop_duplicates("_key").merge(by_code[["_key", *ITEMS]], on="_key")
    b = polys.drop_duplicates("_name").merge(by_name[["_name", *ITEMS]], on="_name")
    b = b[~b["city_code"].isin(a["city_code"])]
    merged = pd.concat([a, b], ignore_index=True)
    unmatched = sorted(set(by_code["city"][~by_code["_key"].isin(a["_key"])]) | set(by_name["city"][~by_name["_name"].isin(b["_name"])]))
    if unmatched:
        print(f"prep   eu_qol_cities: {len(unmatched)} surveyed cities without a boundary polygon (stay missing): {unmatched[:20]}")
    out = gpd.GeoDataFrame(merged[["city_code", "city_name", *ITEMS, "geometry"]], geometry="geometry", crs=polys.crs)
    return out.to_crs(4326) if out.crs is not None else out.set_crs(4326)


def read_table(path: Path, sheet: str | int | None = None) -> pd.DataFrame:
    """The survey file as a DataFrame: .xlsx (``sheet:``), .tsv / .tsv.gz, or CSV (comma or
    semicolon)."""
    name = path.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0, dtype=str)
    if name.endswith((".tsv", ".tsv.gz")):
        return pd.read_csv(path, sep="\t", dtype=str, encoding_errors="replace")
    return pd.read_csv(path, sep=None, engine="python", dtype=str, encoding_errors="replace")


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    table = read_table(settings.raw(source.id) / source.files[0], source.extra.get("sheet"))
    shares = agreement(tidy(table), source.extra.get("items"))
    cities = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]))
    out = attach(shares, cities)
    counts = ", ".join(f"{c} {int(out[c].notna().sum())}" for c in ITEMS)
    print(f"prep   eu_qol_cities: {len(out)} cities with a polygon ({counts})")
    return out
