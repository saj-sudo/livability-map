from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import scoring


def test_percentile_is_midrank_over_domain():
    v = pd.Series([1.0, 2.0, 2.0, 3.0, np.nan, 10.0])
    dom = pd.Series([True, True, True, True, True, False])  # last value has data but sits outside the domain
    s = scoring.percentile_score(v, dom)
    assert s.tolist()[:4] == [12, 50, 50, 88]  # midranks of 1,2,2,3 among 4 -> 0.125, 0.5, 0.5, 0.875
    assert pd.isna(s[4]) and s[5] == 100  # outside-domain value is still scored against the domain
    assert str(s.dtype) == "Int16"


def test_percentile_empty_domain_is_all_null():
    s = scoring.percentile_score(pd.Series([1.0, 2.0]), pd.Series([False, False]))
    assert s.isna().all()


def test_minmax_within_group_uses_distinct_values():
    v = pd.Series([0.6, 0.6, 0.6, 0.82, 5.1, 5.1])
    g = pd.Series(["shdi", "shdi", "shdi", "shdi", "whr", "whr"])
    s = scoring.minmax_score(v, g)
    assert s.tolist() == [0, 0, 0, 100, 50, 50]  # whr has one distinct value -> 50


def test_minmax_ignores_missing_values_and_groups():
    v = pd.Series([1.0, np.nan, 3.0, 2.0])
    g = pd.Series(["a", "a", "a", None])
    s = scoring.minmax_score(v, g)
    assert s.tolist()[0] == 0 and s.tolist()[2] == 100 and pd.isna(s[1]) and pd.isna(s[3])


def test_percentile_against_a_reference_distribution():
    values = pd.Series([1.0, 5.0, 10.0])
    domain = pd.Series([True, True, True])
    ref = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])
    got = scoring.percentile_score(values, domain, reference=ref).tolist()
    assert got == [17, 50, 92]  # midrank of 1, 5 and 10 among the six reference values
    assert scoring.percentile_score(values, domain, reference=np.array([])).isna().all()


def test_minmax_against_reference_bounds():
    ref = pd.DataFrame({"v": [0.2, 0.8], "g": ["shdi", "shdi"]})
    got = scoring.minmax_score(pd.Series([0.5, 0.9]), pd.Series(["shdi", "shdi"]), reference=ref).tolist()
    assert got == [50, 100]  # clipped at the reference maximum


def test_bivariate_cuts_round_trip():
    e = pd.Series([10.0, 50.0, 90.0, 20.0])
    w = pd.Series([90.0, 50.0, 10.0, 80.0])
    inh = pd.Series([True] * 4)
    cuts = scoring.bivariate_cuts(e, w, inh)
    assert scoring.bivariate_class(e, w, inh, cuts=cuts).tolist() == scoring.bivariate_class(e, w, inh).tolist()
    assert scoring.bivariate_cuts(e, w, pd.Series([False] * 4)) is None
