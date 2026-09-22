"""Small helpers shared by the prep loaders: country codes, name normalisation, spreadsheets."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

# Spellings used by WHR / ILOSTAT / OECD that pycountry does not resolve, plus entities without
# an ISO code (None -> dropped with a printed note).
COUNTRY_OVERRIDES: dict[str, str | None] = {
    "Türkiye": "TR",
    "Turkiye": "TR",
    "Turkey": "TR",
    "Kosovo": "XK",
    "Taiwan Province of China": "TW",
    "Taiwan": "TW",
    "Hong Kong SAR of China": "HK",
    "Hong Kong S.A.R. of China": "HK",
    "Congo (Brazzaville)": "CG",
    "Congo (Kinshasa)": "CD",
    "Ivory Coast": "CI",
    "State of Palestine": "PS",
    "Palestinian Territories": "PS",
    "North Cyprus": None,
    "Northern Cyprus": None,
    "Somaliland region": None,
    "Somaliland Region": None,
    "Russia": "RU",
    "Iran": "IR",
    "Syria": "SY",
    "Laos": "LA",
    "Vietnam": "VN",
    "South Korea": "KR",
    "North Korea": "KP",
    "Czechia": "CZ",
    "Eswatini": "SZ",
    "Swaziland": "SZ",
    "Moldova": "MD",
    "Bolivia": "BO",
    "Venezuela": "VE",
    "Tanzania": "TZ",
    "Macedonia": "MK",
    "North Macedonia": "MK",
    "United States": "US",
    "United Kingdom": "GB",
    "Gambia": "GM",
    "Bahamas": "BS",
    "Micronesia": "FM",
    "Cape Verde": "CV",
    "Brunei": "BN",
    "Republic of Korea": "KR",
    "Lao PDR": "LA",
    "Côte d’Ivoire": "CI",
    "Côte d'Ivoire": "CI",
    "DR Congo": "CD",
    "Republic of Moldova": "MD",
    "Viet Nam": "VN",
    "Türkiye (Turkey)": "TR",
}
ISO3_OVERRIDES: dict[str, str] = {"XKX": "XK", "KSV": "XK", "RKS": "XK"}

_unknown_names: set[str] = set()


def country_to_iso2(name: str | None) -> str | None:
    """ISO 3166-1 alpha-2 for a country name as written by data publishers, or None."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    name = str(name).strip()
    if name in COUNTRY_OVERRIDES:
        return COUNTRY_OVERRIDES[name]
    import pycountry

    for getter in (lambda: pycountry.countries.get(name=name), lambda: pycountry.countries.get(official_name=name), lambda: pycountry.countries.get(common_name=name)):
        rec = getter()
        if rec is not None:
            return rec.alpha_2
    try:
        rec = pycountry.countries.lookup(name)
        return rec.alpha_2
    except LookupError:
        pass
    try:
        hits = pycountry.countries.search_fuzzy(name)
    except LookupError:
        hits = []
    # accept a fuzzy hit only when the query is a clean word-subset of the hit's name
    for rec in hits[:1]:
        query = normalize_name(name)
        for attr in ("name", "official_name", "common_name"):
            cand = getattr(rec, attr, None)
            if cand and (normalize_name(cand) == query or query in normalize_name(cand).split()):
                return rec.alpha_2
    if name not in _unknown_names:
        _unknown_names.add(name)
        print(f"prep   note: no ISO code for country name {name!r}; rows dropped")
    return None


def iso3_to_iso2(codes: pd.Series, overrides: dict[str, str] | None = None) -> pd.Series:
    """ISO3 -> ISO2 through pycountry, with overrides for user-assigned codes (fixtures, Kosovo)."""
    try:
        import pycountry
    except ImportError:  # pragma: no cover
        pycountry = None
    table = dict(ISO3_OVERRIDES)
    table.update(overrides or {})
    cache: dict[str, str | None] = {}

    def conv(c):
        if c is None or (isinstance(c, float) and pd.isna(c)):
            return None
        if c in cache:
            return cache[c]
        val = table.get(c)
        if val is None and pycountry is not None:
            rec = pycountry.countries.get(alpha_3=c)
            val = rec.alpha_2 if rec else None
        cache[c] = val
        return val

    return codes.map(conv)


_STOP = {"region", "province", "state", "prefecture", "county", "of", "the", "and", "autonomous", "community", "department", "governorate", "territory", "district", "oblast", "voivodeship"}


def normalize_name(text: str) -> str:
    """Lowercase ASCII with punctuation and generic words removed, for name crosswalks."""
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    words = [w for w in s.split() if w not in _STOP]
    return " ".join(words)


def read_xlsx(path: Path, sheet: str | int, header_row: int = 1) -> pd.DataFrame:
    """A sheet as a DataFrame; ``header_row`` is 1-based (row 7 = the seventh spreadsheet row)."""
    df = pd.read_excel(path, sheet_name=sheet, header=header_row - 1, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def find_column(columns, *candidates: str) -> str:
    """The first column whose lowercase name equals or starts with one of the candidates."""
    lower = {str(c).lower(): str(c) for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    for cand in candidates:
        for lc, orig in lower.items():
            if lc.startswith(cand.lower()):
                return orig
    raise KeyError(f"none of {candidates} found in columns {list(columns)[:30]}")
