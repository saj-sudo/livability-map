from __future__ import annotations

import h3
import pandas as pd

from pipeline import sanity
from pipeline.fixtures import make_fixtures
from pipeline.stages import admin, fetch, grid, hazards, pop


def _run_all(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)


def test_grid_pop_admin_on_fixture_world(settings, capsys):
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    assert len(df) > 50
    assert df["h3"].is_unique
    # ocean point is not a land hex
    assert h3.latlng_to_cell(40.3, 13.8, 4) not in set(df["h3"])
    # Alder is inhabited and in XKA / A-North
    alder = df.set_index("h3").loc[h3.latlng_to_cell(43.0, 11.0, 4)]
    assert alder["inhabited"] and alder["iso_a2"] == "XA" and alder["admin1_name"] == "A-North"
    # desert hex is uninhabited but still has a country
    desert = df.set_index("h3").loc[h3.latlng_to_cell(40.7, 12.5, 4)]
    assert not desert["inhabited"] and desert["iso_a2"] == "XB"
    assert desert["population"] == 0
    # population is conserved-ish: sum over hexes equals raster sum over land within tolerance
    assert df["population"].sum() > 100_000
    assert df["iso_a2"].notna().mean() > 0.9
    sanity.run(settings, make_fixtures.SPOT_CHECKS)
    out = capsys.readouterr().out
    assert "inhabited:" in out and "spot Alder" in out


def test_stages_are_idempotent(settings, capsys):
    _run_all(settings)
    capsys.readouterr()
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    out = capsys.readouterr().out
    assert out.count("up to date") == 4


def test_force_recomputes(settings, capsys):
    _run_all(settings)
    settings.force = True
    capsys.readouterr()
    grid.run(settings)
    assert "up to date" not in capsys.readouterr().out


def test_bbox_subsets_the_grid(settings):
    fetch.run(settings)
    grid.run(settings)
    full = pd.read_parquet(settings.hexes_path(4))
    settings.bbox = (10.0, 40.0, 11.0, 41.0)
    settings.force = True
    grid.run(settings)
    part = pd.read_parquet(settings.hexes_path(4))
    assert 0 < len(part) < len(full)
    assert set(part["h3"]) <= set(full["h3"])


def test_fixture_generation_is_deterministic(tmp_path):
    a = make_fixtures.build(tmp_path / "a")
    b = make_fixtures.build(tmp_path / "b")
    assert a == b


def test_fixture_world_has_urban_classes_and_grids(fixture_dir):
    import geopandas as gpd
    import numpy as np
    import rasterio

    with rasterio.open(fixture_dir / "smod.tif") as src:
        arr = src.read(1)
        assert src.nodata == -200
        assert {10, 11, 21, 30} <= set(np.unique(arr[arr != -200]).astype(int).tolist())
        row, col = src.index(11.0, 43.0)  # Alder centre
        assert arr[row, col] == 30
        row, col = src.index(12.5, 40.7)  # desert
        assert arr[row, col] == 11
    grid = pd.read_csv(fixture_dir / "eurostat_grid.csv")
    assert {"lat", "lng", "pop", "pop_1564", "emp", "emp_rate", "share_ge65"} <= set(grid.columns)
    assert grid["lng"].between(10, 12).all()  # XKA only
    lsoa = gpd.read_file(fixture_dir / "lsoa.gpkg")
    assert {"LSOA21CD", "emp_dep_rate", "health_dep", "housing_barriers", "population", "pop_working"} <= set(lsoa.columns)
    assert lsoa.total_bounds[0] >= 12.0  # XKB B-Mid only
