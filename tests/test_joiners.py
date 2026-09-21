from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline import sanity
from pipeline.joiners import area_weighted_overlay, iso_lookup, point_density, polygon_centroid
from pipeline.stages import admin, fetch, grid, pop


def _hexes(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    return sanity.load_merged(settings, 4)


def test_polygon_centroid_shdi(settings):
    hexes = _hexes(settings)
    regions = gpd.read_file(settings.raw("gdl_shdi_regions") / "shdi_regions.gpkg")
    val = polygon_centroid(hexes, regions, "shdi")
    assert val.index.equals(hexes.index)
    # regions B-Mid and B-South have no SHDI -> NaN there, values elsewhere
    have = hexes.assign(shdi=val)
    assert have.loc[have["admin1_name"] == "A-North", "shdi"].dropna().unique().tolist() == [0.82]
    assert have.loc[have["admin1_name"] == "B-Mid", "shdi"].isna().all()


def test_iso_lookup_whr(settings):
    hexes = _hexes(settings)
    whr = pd.read_csv(settings.raw("whr_ladder") / "whr.csv")
    val = iso_lookup(hexes, whr, "ladder")
    assert set(val.dropna().unique()) == {6.9, 5.1}
    assert (val[hexes["iso_a2"] == "XA"] == 6.9).all()


def test_area_weighted_overlay_tracts(settings):
    hexes = _hexes(settings)
    tracts = gpd.read_file(settings.raw("fixture_tracts") / "tracts.gpkg")
    val = area_weighted_overlay(hexes, tracts, "emp_rate_16_29", weight_field="pop_16_29")
    got = hexes.assign(v=val)
    # only XKB is covered by tracts; XKA hexes away from the border (lng < 11.5) get NaN,
    # hexes straddling the border may legitimately carry a partial-coverage value
    assert got.loc[(got["iso_a2"] == "XA") & (got["lng"] < 11.5), "v"].isna().all()
    xb = got.loc[got["iso_a2"] == "XB", "v"].dropna()
    assert len(xb) > 0 and xb.between(0.549, 0.9).all()  # weighted mean of tract rates in [0.55, 0.9]
    # population-weighting pulls the Cedar hex toward the high-employment tracts
    import h3

    cedar = got.set_index("h3").loc[h3.latlng_to_cell(42.5, 13.0, 4), "v"]
    assert cedar > xb.median()
    plain = area_weighted_overlay(hexes, tracts, "emp_rate_16_29")
    assert np.isfinite(plain.dropna()).all()


def test_point_density_transit(settings):
    hexes = _hexes(settings)
    stops = gpd.read_file(settings.raw("fixture_transit") / "transit_stops.gpkg")
    counts = point_density(hexes, stops, res=4)
    assert counts.sum() == len(stops)
    per_cap = point_density(hexes, stops, res=4, per_capita=True)
    assert per_cap.dropna().max() > 0
    assert per_cap[hexes["population"] == 0].isna().all()
