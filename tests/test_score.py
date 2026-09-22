from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import sanity, scoring
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
    assert inh["coverage"].between(0, 4).all() and inh["bivar"].between(0, 9).all()
    assert df.loc[df["coverage"] == 0, "exposure"].isna().all()
    assert df.loc[df["coverage"] > 0, "exposure"].between(0, 100).all()
    both = inh[inh["exposure"].notna() & inh["wb_score"].notna()]
    assert both["bivar"].between(1, 9).all() and len(both) > 0
    assert inh.loc[inh["wb_score"].isna(), "bivar"].eq(0).all()
    # the desert has wstress -1 -> coverage 3 there, never 0 because of a missing layer
    desert = df[df["admin1_name"] == "B-South"]
    assert (desert.loc[~desert["wstress_ok"], "coverage"] == 3).all()
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
        assert part["jobs_score"].between(0, 100).all() and part["jobs_score"].max() >= 90 and part["jobs_score"].min() <= 30
    # signed dims are clipped integers, composition shares pass through
    assert df["pol_lean"].dropna().between(-100, 100).all() and str(df["pol_lean"].dtype) == "Int16"
    assert (df.loc[df["race_res"] != "none", ["race_w", "race_b", "race_h", "race_a", "race_o"]].sum(axis=1) == 100).all()


def test_no_score_is_zero_because_of_missing_data(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    for hz in ("heat", "rflood", "cflood", "wstress"):
        assert df.loc[~df[f"{hz}_ok"], f"{hz}_score"].isna().all()
    life = [c for c in df.columns if c.endswith("_score") and c[:-6] not in ("heat", "rflood", "cflood", "wstress")]
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
