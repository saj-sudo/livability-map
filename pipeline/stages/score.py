"""``score`` stage (SPEC §5, §8.2, §8.3, §8.4, §20.4): composites and per-dimension scores.

Reads ``hexes ⨝ pop ⨝ admin ⨝ hazards ⨝ dims`` and writes ``data/interim/score_r{res}.parquet``:

- ``coverage``  count of hazard ``_ok`` flags (0-4); ``exposure`` mean of the available hazard
  scores (null when coverage is 0), §8.4
- ``wb_value``, ``wb_score`` (min-max within source, §8.3), ``wb_source`` (``shdi`` | ``whr`` |
  ``none``); ``wb_res`` stays in the dims output
- ``bivar``  3x3 class 1-9 from terciles of exposure and wellbeing over inhabited hexes, 0 when
  either side is missing (§8.4; numbering in ``scoring.bivariate_class``)
- ``{id}_score``  for every life dimension of kind ``score``: midrank percentile within the
  scoring domain of the joiner that supplied the value (``{id}_dom``: global | oecd | us), among
  inhabited hexes (§8.2, §20.4). Uninhabited hexes with a value are scored against the same
  distribution.
- ``scenario``, ``horizon`` constants (§6.1)

Scores are plain percentiles; direction is the client's job (SPEC §13.25). Missing stays
missing (invariant 3). Composition shares pass through untouched from ``dims`` (invariant 8).
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .. import stage_cache
from ..config import Settings
from ..registry import load_dimensions, load_sources
from ..scoring import bivariate_class, minmax_score, percentile_score
from .hazards import HAZARDS

WB_ID = "wb"


def _load(settings: Settings, res: int) -> pd.DataFrame:
    df = pd.read_parquet(settings.hexes_path(res), columns=["h3"])
    for stage in ("pop", "admin", "hazards", "dims"):
        p = settings.stage_path(stage, res)
        if not p.exists():
            raise FileNotFoundError(f"{p} missing (run `{stage}` first)")
        df = df.merge(pd.read_parquet(p), on="h3", how="left")
    df["inhabited"] = df["inhabited"].fillna(False).astype(bool)
    return df.reset_index(drop=True)


def composites(df: pd.DataFrame) -> pd.DataFrame:
    """coverage and exposure from the hazard columns (§8.4)."""
    ok = np.column_stack([df[f"{hz}_ok"].fillna(False).to_numpy(dtype=bool) for hz in HAZARDS])
    scores = np.column_stack([pd.to_numeric(df[f"{hz}_score"], errors="coerce").to_numpy(dtype="float64") for hz in HAZARDS])
    scores = np.where(ok, scores, np.nan)
    coverage = ok.sum(axis=1)
    with np.errstate(invalid="ignore"):
        exposure = np.where(coverage > 0, np.nanmean(np.where(ok, scores, np.nan), axis=1), np.nan)
    out = pd.DataFrame({"h3": df["h3"]})
    out["coverage"] = pd.array(coverage, dtype="Int8")
    out["exposure"] = pd.array(np.round(exposure), dtype="Int16")
    return out


def score_dimension(dim, df: pd.DataFrame) -> dict[str, pd.Series]:
    """Per-domain percentile (or per-source min-max) for one dimension."""
    inhabited = df["inhabited"]
    if dim.scale == "minmax":
        raw = df[f"{dim.id}_raw"]
        return {f"{dim.id}_score": minmax_score(raw, df[f"{dim.id}_lbl"])}
    if dim.kind in ("signed", "composition"):
        return {}  # {id}_lean and the composition shares are final in the dims output (invariant 8)
    raw = pd.to_numeric(df[f"{dim.id}_raw"], errors="coerce")
    dom = df[f"{dim.id}_dom"]
    score = pd.Series(pd.NA, index=df.index, dtype="Int16")
    for d in [x for x in dom.dropna().unique()]:
        in_dom = (dom == d).to_numpy()
        part = percentile_score(raw.where(in_dom), inhabited & in_dom)
        score[in_dom] = part[in_dom]
    return {f"{dim.id}_score": score}


def run(settings: Settings) -> dict[int, dict]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    dims = [d for d in load_dimensions(settings.dimensions_path, sources).values() if d.group != "hazard" and d.joiners]
    report: dict[int, dict] = {}
    for res in settings.res:
        out = settings.stage_path("score", res)
        inputs = [settings.hexes_path(res)] + [settings.stage_path(s, res) for s in ("pop", "admin", "hazards", "dims")]
        params = {"res": res, "bbox": settings.bbox, "stage": "score", "scenario": settings.scenario, "horizon": settings.horizon}
        if stage_cache.is_fresh(out, inputs, params, settings.force):
            print(f"score  res {res}: up to date, skipping")
            report[res] = stage_cache.read_meta(out).get("report", {})
            continue
        t0 = time.time()
        df = _load(settings, res)
        result = composites(df)
        domains: dict[str, dict[str, int]] = {}
        for dim in dims:
            for col, series in score_dimension(dim, df).items():
                result[col] = series
            if dim.kind == "score" and dim.scale != "minmax":
                dom = df[f"{dim.id}_dom"]
                domains[dim.id] = {str(k): int(v) for k, v in dom[df["inhabited"]].value_counts().items()}
        # wellbeing columns per §6.1 (value / score / source / res)
        result["wb_value"] = df[f"{WB_ID}_raw"].astype("float32")
        result["wb_source"] = df[f"{WB_ID}_lbl"].fillna("none").astype(str)
        # wb_res already comes from the dims stage; not repeated here to keep the merge clean
        result["bivar"] = bivariate_class(result["exposure"].astype("float64"), result["wb_score"].astype("float64"), df["inhabited"])
        result["scenario"] = settings.scenario
        result["horizon"] = settings.horizon
        result.to_parquet(out, index=False)
        inh = df["inhabited"].to_numpy(dtype=bool)
        cov = result["coverage"].to_numpy(dtype="float64")
        rep = {
            "domains": domains,
            "inhabited": int(inh.sum()),
            "coverage4_share": float((cov[inh] == 4).mean()) if inh.any() else None,
            "coverage0_share": float((cov[inh] == 0).mean()) if inh.any() else None,
            "bivar_counts": {int(k): int(v) for k, v in result.loc[inh, "bivar"].value_counts().sort_index().items()},
        }
        stage_cache.record(out, inputs, params, {"rows": len(result), "report": rep})
        report[res] = rep
        print(
            f"score  res {res}: coverage=4 {100 * (rep['coverage4_share'] or 0):.1f}% of inhabited, "
            f"bivar classes {rep['bivar_counts']} in {time.time() - t0:.1f}s -> {out.name}"
        )
    return report
