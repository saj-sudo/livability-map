from __future__ import annotations

import h3
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from pipeline import attrs, sanity
from pipeline.stages import admin, fetch, grid, hazards, pop


def _run_all(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)


def _cell(lat, lng):
    return h3.latlng_to_cell(lat, lng, 4)


def test_hazards_on_fixture_world(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4).set_index("h3")
    cedar, desert, north = df.loc[_cell(42.5, 13.0)], df.loc[_cell(40.7, 12.5)], df.loc[_cell(43.7, 10.5)]
    dry = df.loc[_cell(41.34, 10.67)]  # A-South interior: far from the fixture river and the coast
    # riverine: the Cedar floodplain is wet; a dry hex has data and a fraction of exactly 0 (SPEC §8.1)
    assert cedar["rflood_frac"] > 0 and cedar["rflood_ok"]
    assert dry["rflood_frac"] == 0 and dry["rflood_ok"]
    # coastal: a hex on the south-east coast is wet, the interior is dry with data
    assert df.loc[_cell(41.54, 13.65), "cflood_frac"] > 0
    assert dry["cflood_frac"] == 0 and dry["cflood_ok"]
    # heat rises southward in the fixture climatology
    assert desert["heat_days"] > north["heat_days"] and df["heat_ok"].all()
    # water stress: desert is -1 -> stored, not scored (SPEC §8.1); B-North is 4
    assert desert["wstress_cat"] == -1 and not desert["wstress_ok"] and pd.isna(desert["wstress_score"])
    assert df.loc[_cell(43.5, 13.0), "wstress_cat"] == 4 and df.loc[_cell(43.5, 13.0), "wstress_score"] >= 90
    # invariant 3: a score is null exactly when _ok is false; scores stay in 0..100
    for hz in attrs.HAZARD_IDS:
        assert df.loc[~df[f"{hz}_ok"], f"{hz}_score"].isna().all()
        assert df.loc[df[f"{hz}_ok"], f"{hz}_score"].between(0, 100).all()
    # uninhabited hexes with data are still scored against the inhabited distribution
    assert not desert["inhabited"] and pd.notna(desert["heat_score"])


def test_humid_heat_on_fixture_world(settings):
    """Humid heat (SPEC §13.47): hi35 sampled at the centroid like heat, highest on the south-east
    coast, missing (NaN, never 0) in the masked north-west corner."""
    _run_all(settings)
    df = sanity.load_merged(settings, 4).set_index("h3")
    coast, birch = df.loc[_cell(41.5, 13.3)], df.loc[_cell(41.0, 11.5)]
    # near the coast humid heat is far higher than at Birch although their dry heat is close
    assert coast["humid_ok"] and birch["humid_ok"]
    assert coast["humid_days"] > 2 * birch["humid_days"] and coast["humid_score"] > birch["humid_score"]
    assert abs(coast["heat_days"] - birch["heat_days"]) < 5
    # its pattern is not the dry-heat gradient again
    both = df[df["heat_ok"] & df["humid_ok"]]
    assert both["heat_days"].rank().corr(both["humid_days"].rank()) < 0.9
    # the masked corner: no value, not 0, no score; every other hex has one
    gap = df[~df["humid_ok"]]
    assert len(gap) > 0 and gap["humid_days"].isna().all() and gap["humid_score"].isna().all()
    assert (gap["lng"] < 10.75).all() and (gap["lat"] > 43.25).all()
    assert (df.loc[df["humid_ok"], "humid_days"] > 0).all()
    # the raw column, score and flag ship for humid like every hazard, in the stage's order
    assert attrs.HAZARD_IDS == list(hazards.HAZARDS) and attrs.HAZARD_RAW["humid"] == "humid_days"
    assert {"humid_days", "humid_score", "humid_ok"} <= set(attrs.hazard_attrs())


def test_heat_days_variable_fallback(tmp_path):
    """A named variable that is absent falls back only to the single gridded variable."""
    lat, lon = np.array([41.0, 40.0]), np.array([10.0, 11.0])
    grid_ = (("lat", "lon"), np.array([[1.0, 2.0], [3.0, np.nan]], dtype="float32"))
    xr.Dataset({"hi35": grid_}, coords={"lat": lat, "lon": lon}).to_netcdf(tmp_path / "one.nc")
    out = hazards.heat_days(tmp_path / "one.nc", np.array([41.0, 40.0]), np.array([11.0, 11.0]), "climatology-hi35-annual-mean", "hi35")
    assert out[0] == 2.0 and np.isnan(out[1])  # a masked pixel stays NaN, never 0
    assert hazards.heat_days(tmp_path / "one.nc", np.array([40.0]), np.array([10.0]), None, "hi35")[0] == 3.0
    xr.Dataset({"a": grid_, "b": grid_}, coords={"lat": lat, "lon": lon}).to_netcdf(tmp_path / "two.nc")
    with pytest.raises(ValueError, match="no data variable"):
        hazards.heat_days(tmp_path / "two.nc", np.array([40.0]), np.array([10.0]), "missing", "hi35")


def test_hazards_is_idempotent_and_bbox_aware(settings, capsys):
    _run_all(settings)
    capsys.readouterr()
    hazards.run(settings)
    assert "up to date" in capsys.readouterr().out
    full = len(pd.read_parquet(settings.stage_path("hazards", 4)))
    settings.bbox = (12.0, 41.5, 14.0, 43.0)
    settings.force = True
    _run_all(settings)
    part = pd.read_parquet(settings.stage_path("hazards", 4))
    assert 0 < len(part) < full
    assert "bbox" in capsys.readouterr().out.lower()
