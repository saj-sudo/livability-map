"""Reference distributions for derived resolutions (SPEC §13.32).

A derived resolution (a ``children`` entry of the resolution plan, e.g. res 6 or 7) covers only
part of the world, so ranking its hexes among themselves would make a neighbourhood's colour
mean "among urban neighbourhoods" at one zoom and "among all hexes" at another. Instead the
``hazards`` and ``score`` stages rank a derived hex against the inhabited hexes of the finest
complete resolution below it (``plan.reference_res``), read here through ``sanity.load_merged``
so every stage output that exists at the reference is available.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import sanity
from .config import Settings


def reference_inputs(settings: Settings, res: int, stages: tuple[str, ...]) -> list[Path]:
    """The reference files a stage's cache should fingerprint (empty for a complete res)."""
    ref = settings.plan.reference_res(res)
    if ref is None:
        return []
    return [settings.hexes_path(ref)] + [settings.stage_path(s, ref) for s in stages]


def reference_frame(settings: Settings, res: int) -> pd.DataFrame | None:
    """Inhabited hexes of the reference resolution with every stage output that exists, or
    None when ``res`` is complete (it is its own reference)."""
    ref = settings.plan.reference_res(res)
    if ref is None:
        return None
    if not settings.hexes_path(ref).exists() or not settings.stage_path("pop", ref).exists():
        raise FileNotFoundError(f"reference for res {res}: run grid and pop for res {ref} first")
    df = sanity.load_merged(settings, ref)
    return df[df["inhabited"].fillna(False).astype(bool)].reset_index(drop=True)


def require(frame: pd.DataFrame | None, column: str, stage: str, settings: Settings, res: int) -> None:
    """Plain-English guard: the reference must already carry ``column`` (written by ``stage``)."""
    if frame is not None and column not in frame.columns:
        raise FileNotFoundError(f"reference for res {res}: run {stage} for res {settings.plan.reference_res(res)} first")
