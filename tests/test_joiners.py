from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

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


def test_effective_decimate_keeps_a_few_pixels_across_a_hex():
    from pipeline.joiners.raster_mean import effective_decimate

    # h3 v4 average edge lengths: res 5 9.85 km, res 6 3.72 km, res 7 1.41 km
    assert effective_decimate(10, 5, 0.001) == 10
    assert effective_decimate(10, 6, 0.001) == 8
    assert effective_decimate(10, 7, 0.001) == 3
    assert effective_decimate(1, 7, 0.001) == 1


# ---- point_radius (NGO sources after Session 8) --------------------------------------------------


def _hexes_at(points_latlng, res):
    import h3

    cells = [h3.latlng_to_cell(lat, lng, res) for lat, lng in points_latlng]
    lat, lng = zip(*[h3.cell_to_latlng(c) for c in cells], strict=True)
    return pd.DataFrame({"h3": cells, "lat": lat, "lng": lng})


def test_point_radius_sums_within_the_radius_and_zero_means_none_nearby():
    from pipeline.joiners.point_radius import point_radius

    hexes = _hexes_at([(0.0, 0.0), (0.0, 1.0)], 7)
    events = pd.DataFrame({"lat": [0.0, 0.1, 0.0], "lng": [0.05, 0.0, 0.6], "fatal": [2.0, 3.0, 10.0]})
    got = point_radius(hexes, events, 7, "fatal", radius_km=25, agg="sum")
    assert got.iloc[0] == 5.0  # 5.6 km and 11 km away; the third is 66 km away
    assert got.iloc[1] == 0.0  # no event within 25 km: a real zero, not missing


def test_point_radius_mean_is_missing_without_points_and_floors_the_radius_at_the_hex_edge():
    import h3

    from pipeline.joiners.point_radius import point_radius

    hexes = _hexes_at([(0.0, 0.0), (0.0, 1.0)], 4)
    edge = h3.average_hexagon_edge_length(4, unit="km")  # ~22.6 km at res 4
    lat0, lng0 = hexes["lat"].iloc[0], hexes["lng"].iloc[0]
    pts = pd.DataFrame({"lat": [lat0, lat0], "lng": [lng0 + 0.1, lng0 + 0.18], "rwi": [1.0, -1.0], "w": [1.0, 3.0]})  # 11 km and 20 km from the centre
    got = point_radius(hexes, pts, 4, "rwi", radius_km=3, agg="mean", weight_field="w")
    assert edge > 20 and got.iloc[0] == pytest.approx((1.0 * 1 - 1.0 * 3) / 4)  # radius raised to the edge length
    assert pd.isna(got.iloc[1])  # no point near: missing, never 0
