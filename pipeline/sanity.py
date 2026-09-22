"""SPEC §8.5 sanity printouts: coverage and resolution shares, spot checks by place."""

from __future__ import annotations

from dataclasses import dataclass

import h3
import pandas as pd

from .config import Settings


@dataclass(frozen=True)
class Spot:
    name: str
    lat: float
    lng: float
    expect: str


# Real-world spot checks (SPEC §8.5). Fixture spot checks live in pipeline/fixtures.
SPOT_CHECKS = [
    Spot("Dhaka", 23.81, 90.41, "high flood, mid wellbeing"),
    Spot("Phoenix", 33.45, -112.07, "high heat, high wellbeing"),
    Spot("Reykjavik", 64.15, -21.94, "low exposure, high wellbeing"),
    Spot("Sahel (Niamey)", 13.51, 2.12, "water stress + heat, low wellbeing"),
]


def load_merged(settings: Settings, res: int) -> pd.DataFrame:
    """Join every interim stage output that exists for this resolution on h3."""
    df = pd.read_parquet(settings.hexes_path(res))
    for stage in ("pop", "admin", "hazards", "dims", "score"):
        p = settings.stage_path(stage, res)
        if p.exists():
            df = df.merge(pd.read_parquet(p), on="h3", how="left")
    return df


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):5.1f}%" if d else "  n/a"


def print_counts(df: pd.DataFrame, res: int) -> None:
    total = len(df)
    print(f"sanity res {res}: {total} land hexes")
    if "inhabited" in df.columns:
        inh = df[df["inhabited"]]
        print(f"  inhabited: {len(inh)} ({_pct(len(inh), total)})")
    else:
        inh = df
    if "coverage" in df.columns:
        for k in (4, 0):
            print(f"  inhabited with coverage = {k}: {_pct(int((inh['coverage'] == k).sum()), len(inh))}")
    for hz in ("heat", "rflood", "cflood", "wstress"):
        if f"{hz}_ok" in df.columns:
            print(f"  inhabited with {hz}_ok: {_pct(int(inh[f'{hz}_ok'].sum()), len(inh))}")
    if "wb_res" in df.columns:
        for tag, n in inh["wb_res"].fillna("none").value_counts().items():
            print(f"  inhabited by wb_res {tag:9s}: {_pct(int(n), len(inh))}")
    for col in sorted(c for c in df.columns if c.endswith("_res") and c != "wb_res"):
        for tag, n in inh[col].fillna("none").value_counts().items():
            print(f"  inhabited by {col:10s} {tag:9s}: {_pct(int(n), len(inh))}")
    if "iso_a2" in df.columns:
        print(f"  with country: {_pct(int(df['iso_a2'].notna().sum()), total)}; with admin1: {_pct(int(df['admin1_id'].notna().sum()), total)}")


def _plain(v):
    """JSON-friendly scalar: numpy -> python, NaN / NA -> None."""
    if v is pd.NA:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v != v:
        return None
    return v


def spot_row(df: pd.DataFrame, res: int, spot: Spot, max_ring: int = 2) -> tuple[str, str, dict] | None:
    """The hex for a spot check: the cell containing the point, or the nearest land hex within
    ``max_ring`` rings (coastal places often sit in a cell whose centre is at sea, a known gap of
    the SPEC §5 grid). Returns (cell, note, attributes) or None when nothing is near."""
    idx = df if df.index.name == "h3" else df.set_index("h3")
    cell = h3.latlng_to_cell(spot.lat, spot.lng, res)
    note = ""
    if cell not in idx.index:
        near = [c for k in range(1, max_ring + 1) for c in sorted(h3.grid_ring(cell, k)) if c in idx.index]
        if not near:
            return None
        cell, note = near[0], " (nearest land hex)"
    row = idx.loc[cell]
    shown = {k: _plain(row[k]) for k in row.index if k not in ("lat", "lng", "res")}
    return cell, note, shown


def spot_check(df: pd.DataFrame, res: int, spots: list[Spot]) -> None:
    idx = df.set_index("h3")
    for s in spots:
        found = spot_row(idx, res, s)
        if found is None:
            print(f"  spot {s.name:16s} {h3.latlng_to_cell(s.lat, s.lng, res)}: not a land hex in this run")
            continue
        cell, note, shown = found
        print(f"  spot {s.name:16s}{note} expect [{s.expect}] -> {shown}")


def run(settings: Settings, spots: list[Spot] | None = None) -> None:
    for res in settings.res:
        if not settings.hexes_path(res).exists():
            print(f"sanity res {res}: no hexes yet")
            continue
        df = load_merged(settings, res)
        print_counts(df, res)
        spot_check(df, res, spots if spots is not None else SPOT_CHECKS)
