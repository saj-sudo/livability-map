"""Cross-check our hazard scores against FEMA's National Risk Index (SPEC §16 "Check against FEMA
NRI"), for the first real build with `nri` on the map (§13.38).

    uv run python -m pipeline.nri_check [--fixtures] [--res 5]

For every inhabited hex that has an NRI tract value, it correlates (Spearman, rank based like the
scores) the riverine, coastal and heat scores with the NRI building loss rate for the same hazard
and with the all-hazard rate, overall and by state, and prints a markdown table to paste into
SPEC §15 beside the §8.5 spot checks.

The constructs differ (present-day loss vs 2050 exposure), so this looks for sign errors and gross
misses, not a tight fit: a negative correlation, or one near zero, is flagged "look here", never
failed. The exit status is non-zero only when an input is missing. Hexes without an NRI value for
a hazard (not applicable there) are left out of that hazard's rows, not counted as zero.

It reuses the `dims` overlay (`run_joiner`) so a tract value reaches a hex exactly as `nri` does.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import prep, sanity
from .config import Settings, find_root
from .registry import JoinSpec, load_sources
from .stages import dims

# (our score column, label, NRI column prepared by prep/fema_nri.py for the same hazard)
HAZARDS = [
    ("rflood_score", "riverine flood", "rflood_per_1k"),
    ("cflood_score", "coastal flood", "cflood_per_1k"),
    ("heat_score", "heat", "heat_per_1k"),
]
ALL_HAZARD = "loss_per_1k"
WEAK = 0.10  # |rho| under this reads as "no relationship"
MIN_STATE_HEXES = 30  # states with fewer paired hexes are not listed


@dataclass(frozen=True)
class Row:
    hazard: str
    measure: str  # "same hazard" | "all hazards"
    where: str  # "all US" or a state name
    n: int
    rho: float
    flag: str  # "ok" | "weak" | "look here (negative)"


def spearman(a: pd.Series, b: pd.Series) -> tuple[int, float]:
    """(pairs, Spearman rho) over the rows where both exist; NaN when there are too few or either
    side is constant."""
    both = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(both) < 3 or both["a"].nunique() < 2 or both["b"].nunique() < 2:
        return len(both), float("nan")
    return len(both), float(both["a"].rank().corr(both["b"].rank()))


def flag(rho: float) -> str:
    if np.isnan(rho):
        return "n/a"
    if rho < -WEAK:
        return "look here (negative)"  # a sign error would show as a clearly negative rank correlation
    return "weak" if rho < WEAK else "ok"


def rates_on_hexes(settings: Settings, hexes: pd.DataFrame, res: int, fields: list[str]) -> pd.DataFrame:
    """The NRI tract columns in ``fields`` laid onto ``hexes`` the way the `nri` dimension does
    (population-weighted tract overlay); a column the prepared layer lacks is simply absent."""
    sources = load_sources(settings.sources_path)
    layer = prep.load_layer(settings, "fema_nri", sources)
    layer = dims._as_wgs84(layer)
    out = {}
    for field in fields:
        if field not in layer.columns:
            continue
        spec = JoinSpec(source="fema_nri", joiner="area_weighted_overlay", res="tract", field=field, weight_field="population")
        out[field] = pd.Series(dims.run_joiner(spec, hexes, layer, res, field), index=hexes.index)
    return pd.DataFrame(out, index=hexes.index)


def correlate(df: pd.DataFrame, by: str = "admin1_name") -> list[Row]:
    """Rows for ``df``: one hex per row with our ``*_score`` columns, ``loss_per_1k`` and the
    hazard rates. Hazards whose score or NRI rate column is absent are skipped."""
    rows: list[Row] = []
    for score, label, rate in HAZARDS:
        if score not in df.columns:
            continue
        for measure, col in (("same hazard", rate), ("all hazards", ALL_HAZARD)):
            if col not in df.columns:
                continue
            n, rho = spearman(df[score], df[col])
            rows.append(Row(label, measure, "all US", n, rho, flag(rho)))
            if by in df.columns:
                for state, part in df.groupby(by):
                    n, rho = spearman(part[score], part[col])
                    if n >= MIN_STATE_HEXES:
                        rows.append(Row(label, measure, str(state), n, rho, flag(rho)))
    return rows


def markdown(rows: list[Row], res: int, built: str = "") -> str:
    lines = [
        f"NRI cross-check, res {res}{(' (' + built + ')') if built else ''}: Spearman rho between our score and the NRI building loss rate, inhabited hexes with a tract value.",
        "",
        "| Hazard | NRI measure | Area | Hexes | rho | Flag |",
        "|---|---|---|---:|---:|---|",
    ]
    for r in rows:
        rho = "n/a" if np.isnan(r.rho) else f"{r.rho:+.2f}"
        lines.append(f"| {r.hazard} | {r.measure} | {r.where} | {r.n} | {rho} | {r.flag} |")
    return "\n".join(lines)


def run(settings: Settings, res: int) -> list[Row]:
    """Build the paired frame for ``res`` and correlate it. Raises FileNotFoundError when a stage
    output or the NRI layer is missing."""
    for stage in ("hazards", "dims"):
        if not settings.stage_path(stage, res).exists():
            raise FileNotFoundError(f"{settings.stage_path(stage, res)} missing: run the pipeline through `dims` at res {res} first")
    merged = sanity.load_merged(settings, res)
    if "nri_res" not in merged.columns:
        raise FileNotFoundError("the dims output has no `nri` dimension; rebuild `dims`")
    paired = merged[merged["inhabited"].fillna(False).astype(bool) & (merged["nri_res"] == "tract")].reset_index(drop=True)
    if paired.empty:
        raise FileNotFoundError(f"no inhabited hex at res {res} has an NRI tract value (is the `fema_nri` layer prepared and covering the area?)")
    paired["loss_per_1k"] = paired["nri_raw"].astype("float64")
    extra = rates_on_hexes(settings, paired, res, [rate for _, _, rate in HAZARDS])
    paired = pd.concat([paired, extra], axis=1)
    missing = [rate for _, _, rate in HAZARDS if rate not in paired.columns]
    if missing:
        print(f"nri_check: the prepared NRI layer has no {', '.join(missing)}; only the all-hazard rate is compared for those hazards.", file=sys.stderr)
    return correlate(paired)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Correlate our hazard scores with FEMA NRI building loss rates.")
    ap.add_argument("--fixtures", action="store_true", help="use the synthetic fixture world")
    ap.add_argument("--res", type=int, help="resolution to check (default: the finest complete one, res 5)")
    args = ap.parse_args(argv)
    settings = Settings(root=find_root(), fixtures=args.fixtures)
    if args.fixtures:
        from .fixtures import make_fixtures

        make_fixtures.ensure(settings.fixture_data_dir)
        make_fixtures.apply(settings)
    res = args.res or (4 if args.fixtures else 5)
    try:
        rows = run(settings, res)
    except FileNotFoundError as exc:
        print(f"nri_check stopped: {exc}", file=sys.stderr)
        return 1
    print(markdown(rows, res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
