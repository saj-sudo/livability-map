from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import sanity, scoring
from pipeline.attrs import HAZARD_IDS
from pipeline.stages import admin, dims, fetch, grid, hazards, pop, score


def _run_all(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)
    score.run(settings)


def test_composites_and_bivar(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    inh = df[df["inhabited"]]
    assert len(HAZARD_IDS) == 5  # humid heat is the fifth hazard (SPEC §13.47)
    assert inh["coverage"].between(0, 5).all() and inh["bivar"].between(0, 9).all()
    assert (inh["coverage"] == 5).any() and (inh["coverage"] == 4).any()  # full coverage is reachable; the masked hi35 corner is not
    assert df.loc[df["coverage"] == 0, "exposure"].isna().all()
    assert df.loc[df["coverage"] > 0, "exposure"].between(0, 100).all()
    both = inh[inh["exposure"].notna() & inh["wb_score"].notna()]
    assert both["bivar"].between(1, 9).all() and len(both) > 0
    assert inh.loc[inh["wb_score"].isna(), "bivar"].eq(0).all()
    # the desert has wstress -1 -> coverage 4 there, never 0 because of a missing layer
    desert = df[df["admin1_name"] == "B-South"]
    assert (desert.loc[~desert["wstress_ok"], "coverage"] == 4).all()
    # exposure is the mean of all five hazard scores where every layer is present: dry heat and
    # humid heat both count, so heat weighs twice (§13.47)
    full = df[df["coverage"] == 5]
    mean5 = full[[f"{hz}_score" for hz in HAZARD_IDS]].astype("float64").mean(axis=1)
    assert len(full) > 0 and (full["exposure"].astype("float64") - mean5).abs().max() <= 0.5
    # where humid heat is missing the mean runs over the other four, never a 0 for the gap
    part = df[(df["coverage"] == 4) & ~df["humid_ok"]]
    mean4 = part[[f"{hz}_score" for hz in HAZARD_IDS if hz != "humid"]].astype("float64").mean(axis=1)
    assert len(part) > 0 and (part["exposure"].astype("float64") - mean4).abs().max() <= 0.5
    # wb min-max within source: A-North (0.82) is the SHDI max, B-North (0.60) the min
    assert (df.loc[df["admin1_name"] == "A-North", "wb_score"] == 100).all()
    assert (df.loc[df["admin1_name"] == "B-North", "wb_score"] == 0).all()
    assert (df.loc[df["wb_res"] == "national", "wb_source"] == "whr").all()
    assert (df.loc[df["wb_res"] == "admin1", "wb_source"] == "shdi").all()
    assert (df["scenario"] == "rcp45_ssp245").all() and (df["horizon"] == "2050").all()


def test_life_dimension_scores_are_per_domain(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    inh = df[df["inhabited"]]
    # jobs has two domains in the fixture world (oecd for XKA, us for XKB); each is ranked on its own
    for dom in ("oecd", "us"):
        part = inh[inh["jobs_dom"] == dom]
        assert part["jobs_score"].between(0, 100).all() and part["jobs_score"].nunique() >= 2
        # the best raw value in the domain carries the best score (midrank: ties share a score)
        assert part.loc[part["jobs_raw"].idxmax(), "jobs_score"] == part["jobs_score"].max()
        assert part.loc[part["jobs_raw"].idxmin(), "jobs_score"] == part["jobs_score"].min()
    # signed dims are clipped integers, composition shares pass through
    assert df["pol_lean"].dropna().between(-100, 100).all() and str(df["pol_lean"].dtype) == "Int16"
    assert (df.loc[df["race_res"] != "none", ["race_w", "race_b", "race_h", "race_a", "race_o"]].sum(axis=1) == 100).all()


def test_no_score_is_zero_because_of_missing_data(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    for hz in HAZARD_IDS:
        assert df.loc[~df[f"{hz}_ok"], f"{hz}_score"].isna().all()
    life = [c for c in df.columns if c.endswith("_score") and c[:-6] not in HAZARD_IDS]
    assert life, "no life dimension scores found"
    for col in life:
        tag = df[col[:-6] + "_res"]
        assert df.loc[tag == "none", col].isna().all(), col
        assert df.loc[tag != "none", col].notna().all(), col


def test_bivariate_class_numbering():
    exp = pd.Series([0, 50, 100, 0, 50, 100, 0, 50, 100, np.nan])
    wb = pd.Series([0, 0, 0, 50, 50, 50, 100, 100, 100, 50])
    assert scoring.bivariate_class(exp, wb, pd.Series([True] * 10)).tolist() == [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]


def test_score_is_idempotent(settings, capsys):
    _run_all(settings)
    capsys.readouterr()
    score.run(settings)
    assert "up to date" in capsys.readouterr().out


def test_opposite_direction_joiner_is_reflected():
    from pipeline.registry import Dimension, JoinSpec

    # a dimension where higher is better fed by a deprivation rate (higher = worse): raw 10 (worst) scores lowest
    dim = Dimension(id="d", name="d", group="life", kind="score", higher_is="better", joiners=[JoinSpec(source="s", joiner="polygon_centroid", res="tract", field="f", domain="x", label="imd", higher_is="worse")])
    df = pd.DataFrame({"d_raw": [1.0, 10.0, 5.0], "d_dom": ["x"] * 3, "d_lbl": ["imd"] * 3, "inhabited": [True] * 3})
    s = score.score_dimension(dim, df)["d_score"].tolist()
    assert s[0] > s[2] > s[1]
