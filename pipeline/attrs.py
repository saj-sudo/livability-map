"""Which hex attributes ship in the vector tiles, and how they are rounded (SPEC §6.1, §9.2).

Everything §6.1 lists ships; the pipeline-internal columns (``lat``, ``lng``, ``iso_a3``,
``{id}_src``, ``{id}_dom``, ``{id}_lbl``) stay in the parquet. Null attributes cost nothing in
MVT, so missing values are simply absent from the feature (invariant 3: never 0).
"""

from __future__ import annotations

import math

from .registry import COMPOSITION_KEYS, Dimension

BASE_ATTRS = ["h3", "res", "iso_a2", "admin1_id", "admin1_name", "population", "inhabited"]
HAZARD_IDS = ["heat", "rflood", "cflood", "wstress"]
HAZARD_RAW = {"heat": "heat_days", "rflood": "rflood_frac", "cflood": "cflood_frac", "wstress": "wstress_cat"}
COMPOSITE_ATTRS = ["coverage", "exposure", "wb_value", "wb_score", "wb_source", "wb_res", "bivar", "scenario", "horizon"]
PARQUET_ONLY_SUFFIXES = ("_src", "_dom", "_lbl")

# decimals kept for floats that ship in tiles; anything else float is rounded to 3 significant digits
ATTR_ROUNDING = {"heat_days": 1, "rflood_frac": 3, "cflood_frac": 3, "wb_value": 3}


def hazard_attrs() -> list[str]:
    out = []
    for hz in HAZARD_IDS:
        out += [HAZARD_RAW[hz], f"{hz}_score", f"{hz}_ok"]
    return out


def dimension_attrs(dim: Dimension) -> list[str]:
    """Tile columns for one life dimension (hazards and wellbeing are handled above)."""
    if dim.group == "hazard" or dim.id == "wb":
        return []
    if dim.kind == "score":
        return [f"{dim.id}_raw", f"{dim.id}_score", f"{dim.id}_res"]
    if dim.kind == "signed":
        return [f"{dim.id}_lean", f"{dim.id}_res"]
    return [f"{dim.id}_{k}" for k in COMPOSITION_KEYS] + [f"{dim.id}_maj", f"{dim.id}_res"]


def tile_attrs(dims: dict[str, Dimension]) -> list[str]:
    """Every attribute that ships in tiles, in a stable order."""
    out = list(BASE_ATTRS) + hazard_attrs() + list(COMPOSITE_ATTRS)
    for dim in dims.values():
        out += dimension_attrs(dim)
    return out


def style_attrs(dims: dict[str, Dimension]) -> list[str]:
    """The slim subset a style expression needs (used for the fattest low-zoom tiles only when
    the size guard in the tiles stage asks for it): no raw values, no strings but the res tags."""
    out = ["inhabited", "coverage", "exposure", "wb_score", "wb_res", "bivar"]
    out += [f"{hz}_score" for hz in HAZARD_IDS] + [f"{hz}_ok" for hz in HAZARD_IDS]
    for dim in dims.values():
        if dim.group == "hazard" or dim.id == "wb":
            continue
        if dim.kind == "score":
            out += [f"{dim.id}_score", f"{dim.id}_res"]
        elif dim.kind == "signed":
            out += [f"{dim.id}_lean", f"{dim.id}_res"]
        else:
            out += [f"{dim.id}_{k}" for k in COMPOSITION_KEYS] + [f"{dim.id}_res"]
    return out


def round_value(name: str, value):
    """Round a float attribute for tiles; ints, bools and strings pass through."""
    if isinstance(value, bool) or not isinstance(value, float):
        return value
    if math.isnan(value):
        return None
    if name in ATTR_ROUNDING:
        return round(value, ATTR_ROUNDING[name])
    if name.endswith("_raw"):
        return float(f"{value:.3g}")
    return round(value, 3)
