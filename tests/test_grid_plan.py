"""``grid`` stage with the resolution plan (SPEC §9.1, §13.32): derived resolutions are the H3
children of parent cells that match a country or urban rule; children off land are dropped."""

from __future__ import annotations

import h3
import pandas as pd
import pytest

from pipeline.stages import admin, fetch, grid, pop, urban


def _prepare(settings, res):
    settings.res = res
    fetch.run(settings)
    urban.run(settings)
    grid.run(settings)


def test_children_only_where_the_plan_says(settings):
    _prepare(settings, [4, 5, 6, 7])
    r5 = pd.read_parquet(settings.hexes_path(5))
    r6 = pd.read_parquet(settings.hexes_path(6))
    r7 = pd.read_parquet(settings.hexes_path(7))
    assert set(r6["parent"]) <= set(r5["h3"]) and set(r7["parent"]) <= set(r6["h3"])
    assert (r6["h3"].map(lambda c: h3.cell_to_parent(c, 5)) == r6["parent"]).all()
    alder7 = h3.latlng_to_cell(43.0, 11.0, 7)
    assert alder7 in set(r7["h3"])
    assert h3.latlng_to_cell(40.7, 12.5, 7) not in set(r7["h3"])  # desert: no urban centre
    assert h3.latlng_to_cell(42.5, 13.0, 6) in set(r6["h3"])  # Cedar (XB): refined through its cluster
    assert h3.latlng_to_cell(40.7, 12.5, 6) not in set(r6["h3"])  # desert in XB: no rule matches
    assert h3.latlng_to_cell(41.0, 10.5, 6) in set(r6["h3"])  # rural XA: the country rule
    assert r7.set_index("h3").loc[alder7, "uc_id"] in (1, 2, 3)
    assert r7["uc_id"].notna().any() and r7["uc_id"].isna().any()  # only children centred inside a centre carry its id
    assert r6["uc_id"].isna().any()  # country-rule children outside any cluster carry no id
    assert list(r7.columns) == ["h3", "res", "lat", "lng", "parent", "uc_id"]


def test_children_with_an_ocean_centre_are_dropped(settings):
    _prepare(settings, [4, 5, 6])
    r6 = pd.read_parquet(settings.hexes_path(6))
    assert h3.latlng_to_cell(40.3, 13.8, 6) not in set(r6["h3"])


def test_missing_parent_is_a_plain_error(settings):
    settings.res = [7]
    fetch.run(settings)
    urban.run(settings)
    with pytest.raises(FileNotFoundError, match="run grid for res 6 first"):
        grid.run(settings)


def test_missing_urban_layer_is_a_plain_error(settings):
    settings.res = [4, 5, 6]
    fetch.run(settings)
    with pytest.raises(FileNotFoundError, match="run `urban` first"):
        grid.run(settings)


def test_derived_grid_is_cached_and_rebuilt_on_force(settings, capsys):
    _prepare(settings, [4, 5, 6])
    capsys.readouterr()
    grid.run(settings)
    assert capsys.readouterr().out.count("up to date") == 3
    settings.force = True
    grid.run(settings)
    assert "up to date" not in capsys.readouterr().out


def test_downstream_stages_run_on_a_derived_resolution(settings):
    _prepare(settings, [4, 5, 6, 7])
    pop.run(settings)
    admin.run(settings)
    p7 = pd.read_parquet(settings.stage_path("pop", 7))
    assert p7["population"].sum() > 0 and p7["inhabited"].any()
    a7 = pd.read_parquet(settings.stage_path("admin", 7))
    assert a7["iso_a2"].notna().all()
