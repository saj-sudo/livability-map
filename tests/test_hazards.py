from __future__ import annotations

import h3
import pandas as pd

from pipeline import sanity
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
    for hz in ("heat", "rflood", "cflood", "wstress"):
        assert df.loc[~df[f"{hz}_ok"], f"{hz}_score"].isna().all()
        assert df.loc[df[f"{hz}_ok"], f"{hz}_score"].between(0, 100).all()
    # uninhabited hexes with data are still scored against the inhabited distribution
    assert not desert["inhabited"] and pd.notna(desert["heat_score"])


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
