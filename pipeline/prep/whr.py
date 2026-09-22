"""World Happiness Report "Data for Figure 2.1" -> national ladder table (SPEC §7, §15.5).

The 2026 file is a 2011-2025 panel with columns ``Year, Rank, Country name,
Life evaluation (3-year average), ...``. We keep the latest year and map country names to
ISO2 so ``iso_lookup`` can join on the hex's ``iso_a2``.
"""

from __future__ import annotations

import pandas as pd

from ..config import Settings
from ..registry import Source
from .util import country_to_iso2, find_column, read_xlsx


def load(settings: Settings, source: Source, sources: dict[str, Source]) -> pd.DataFrame:
    path = settings.raw(source.id) / source.files[0]
    df = read_xlsx(path, source.extra.get("sheet", 0), int(source.extra.get("header_row", 1)))
    year_col = find_column(df.columns, "Year")
    name_col = find_column(df.columns, "Country name", "Country")
    ladder_col = find_column(df.columns, "Life evaluation", "Ladder score", "Ladder")
    df = df[[year_col, name_col, ladder_col]].rename(columns={year_col: "year", name_col: "country", ladder_col: "ladder"})
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["ladder"] = pd.to_numeric(df["ladder"], errors="coerce")
    df = df.dropna(subset=["year", "ladder"])
    latest = int(df["year"].max())
    df = df[df["year"] == latest].copy()
    df["iso_a2"] = df["country"].map(country_to_iso2)
    df = df.dropna(subset=["iso_a2"]).drop_duplicates(subset=["iso_a2"])
    df["year"] = df["year"].astype(int)
    print(f"prep   whr_ladder: {len(df)} countries for {latest}")
    return df[["iso_a2", "country", "ladder", "year"]].reset_index(drop=True)
