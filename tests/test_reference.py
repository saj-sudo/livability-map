"""Reference-distribution scoring for derived resolutions (SPEC §13.32)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline import sanity
from pipeline.stages import admin, dims, fetch, grid, hazards, pop, score, urban


def _run(settings, *stages):
    for stage in stages:
        stage.run(settings)


def test_derived_resolution_scores_use_the_res5_distribution(settings):
    settings.res = [4, 5, 6, 7]
    _run(settings, fetch, urban, grid, pop, admin, hazards, dims, score)
    r5 = sanity.load_merged(settings, 5)
    r7 = sanity.load_merged(settings, 7)
    ref = np.sort(r5.loc[r5["inhabited"] & r5["heat_ok"], "heat_days"].to_numpy(dtype="float64"))
    row = r7[r7["heat_ok"]].iloc[0]
    v = float(row["heat_days"])
    expect = int(round(100 * (np.searchsorted(ref, v, "left") + np.searchsorted(ref, v, "right")) / (2 * len(ref))))
    assert int(row["heat_score"]) == expect
    assert r7["jobs_score"].dropna().between(0, 100).all() and r7["bivar"].isin(range(10)).all()
    assert r7["wb_score"].notna().any()


def test_missing_reference_is_a_plain_error(settings):
    settings.res = [4, 5, 6]
    _run(settings, fetch, urban, grid, pop, admin)
    settings.res = [6]
    with pytest.raises(FileNotFoundError, match="run hazards for res 5 first"):
        hazards.run(settings)


def test_empty_reference_domain_leaves_scores_missing(settings):
    # A derived hex whose domain has no reference value: score stays NA, never 0. Simulated by
    # blanking the `oecd` domain out of the res-5 dims parquet before scoring res 6.
    settings.res = [4, 5, 6]
    _run(settings, fetch, urban, grid, pop, admin, hazards, dims)
    settings.res = [4, 5]
    score.run(settings)  # the reference needs its own scores (bivariate cuts) before res 6 is scored
    p5 = settings.stage_path("dims", 5)
    d5 = pd.read_parquet(p5)
    d5.loc[d5["jobs_dom"] == "oecd", "jobs_raw"] = np.nan
    d5.to_parquet(p5, index=False)
    settings.res = [6]
    score.run(settings)
    r6 = sanity.load_merged(settings, 6)
    assert (r6["jobs_dom"] == "oecd").any()
    assert r6.loc[r6["jobs_dom"] == "oecd", "jobs_score"].isna().all()
    assert r6.loc[(r6["jobs_dom"] != "oecd") & r6["jobs_raw"].notna(), "jobs_score"].notna().any()
