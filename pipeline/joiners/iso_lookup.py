"""``iso_lookup``: national table value by country code (``iso_a2`` on the hex)."""

from __future__ import annotations

import pandas as pd


def iso_lookup(hexes: pd.DataFrame, table: pd.DataFrame, field: str, iso_col: str = "iso_a2", hex_iso_col: str = "iso_a2") -> pd.Series:
    if hex_iso_col not in hexes.columns:
        raise KeyError(f"hexes need a {hex_iso_col!r} column (run `admin` first)")
    if iso_col not in table.columns or field not in table.columns:
        raise KeyError(f"table needs columns {iso_col!r} and {field!r}; has {list(table.columns)}")
    lookup = table.drop_duplicates(subset=[iso_col]).set_index(iso_col)[field]
    out = hexes[hex_iso_col].map(lookup)
    out.name = field
    return out
