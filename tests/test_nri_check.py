from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import nri_check
from pipeline.stages import admin, dims, fetch, grid, hazards, pop, score


def test_spearman_is_rank_based_and_needs_pairs():
    a = pd.Series([1, 2, 3, 4, 5, np.nan])
    n, rho = nri_check.spearman(a, pd.Series([1, 10, 100, 1000, 10000, 5]))  # monotonic but far from linear
    assert n == 5 and rho == pytest.approx(1.0)
    assert nri_check.spearman(pd.Series([1, 2, 3, 4]), pd.Series([40, 30, 20, 10]))[1] == pytest.approx(-1.0)
    n, rho = nri_check.spearman(pd.Series([1, 1, 1, 1]), pd.Series([1, 2, 3, 4]))
    assert n == 4 and np.isnan(rho)  # a constant side has no correlation
    assert np.isnan(nri_check.spearman(pd.Series([1, 2]), pd.Series([2, 1]))[1])  # two pairs are not evidence


def test_flags_separate_a_sign_error_from_noise():
    assert nri_check.flag(0.45) == "ok"
    assert nri_check.flag(0.05) == "weak" and nri_check.flag(-0.05) == "weak"  # no relationship is not a sign error
    assert nri_check.flag(-0.4) == "look here (negative)"
    assert nri_check.flag(float("nan")) == "n/a"


def _paired(n=120, seed=1):
    rng = np.random.default_rng(seed)
    base = rng.uniform(0, 100, n)
    return pd.DataFrame({
        "admin1_name": np.where(np.arange(n) < 60, "Alpha", "Beta"),
        "rflood_score": base,
        "rflood_per_1k": base * 0.01 + rng.normal(0, 0.05, n),  # agrees with our score
        "cflood_score": base,
        "cflood_per_1k": -base * 0.01,  # a sign error: our score rises where NRI losses fall
        "heat_score": base,
        "heat_per_1k": np.where(np.arange(n) < 60, base, np.nan),  # NRI not applicable in Beta
        "loss_per_1k": rng.uniform(0, 1, n),  # unrelated
    })


def test_correlate_reports_each_hazard_overall_and_by_state():
    rows = nri_check.correlate(_paired())
    by = {(r.hazard, r.measure, r.where): r for r in rows}
    assert by[("riverine flood", "same hazard", "all US")].flag == "ok"
    assert by[("coastal flood", "same hazard", "all US")].flag == "look here (negative)"
    assert by[("coastal flood", "same hazard", "Alpha")].rho == pytest.approx(-1.0)
    assert by[("riverine flood", "all hazards", "all US")].flag == "weak"
    heat = by[("heat", "same hazard", "all US")]
    assert heat.n == 60 and ("heat", "same hazard", "Beta") not in by  # not-applicable hexes are left out, and a state with no pairs is not listed


def test_correlate_skips_hazards_without_their_columns_and_small_states():
    df = _paired().drop(columns=["cflood_per_1k", "heat_per_1k"])
    df.loc[df.index[:100], "admin1_name"] = "Big"  # leaves only 20 hexes in the other state: under MIN_STATE_HEXES
    rows = nri_check.correlate(df)
    assert {r.hazard for r in rows if r.measure == "same hazard"} == {"riverine flood"}
    assert {r.where for r in rows} == {"all US", "Big"}


def test_markdown_table_shape():
    text = nri_check.markdown(nri_check.correlate(_paired()), 5, built="test")
    lines = text.splitlines()
    assert lines[2].startswith("| Hazard |") and lines[3].startswith("|---")
    assert all(line.count("|") == 7 for line in lines[2:])
    assert "res 5 (test)" in lines[0] and "-1.00" in text


def _through_dims(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)
    score.run(settings)


def test_run_on_the_fixture_world_pairs_tract_hexes(settings):
    _through_dims(settings)
    rows = nri_check.run(settings, 4)
    same = [r for r in rows if r.measure == "same hazard" and r.where == "all US"]
    assert {r.hazard for r in same} == {"riverine flood", "coastal flood", "heat", "humid heat"}
    assert all(r.n > 10 and not np.isnan(r.rho) for r in same)  # the fixture tracts cover Cedaria's hexes


def test_main_exits_non_zero_only_when_an_input_is_missing(settings, capsys, monkeypatch):
    monkeypatch.setattr(nri_check, "Settings", lambda **kw: settings)
    assert nri_check.main(["--fixtures", "--res", "4"]) == 1  # nothing built yet
    assert "nri_check stopped" in capsys.readouterr().err
    _through_dims(settings)
    assert nri_check.main(["--fixtures", "--res", "4"]) == 0  # a weak or negative rho never fails the run
    assert "| Hazard |" in capsys.readouterr().out
