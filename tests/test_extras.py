"""The hex-level extras (SPEC §20.6, 2026-09-22): raster_mean / point_mean joiners, the raster
builders, the Ookla and Aqueduct loaders, and the six dimensions on the fixture world."""

from __future__ import annotations

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pytest
import rasterio
import xarray as xr
from rasterio.transform import from_origin
from shapely.geometry import box

from pipeline import h3util, sanity
from pipeline.joiners import point_mean, raster_mean
from pipeline.prep import aqueduct, ookla, rasters
from pipeline.stages import admin, dims, fetch, grid, hazards, pop


def _run_all(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)


def _cell(lat, lng):
    return h3.latlng_to_cell(lat, lng, 4)


def _write(path, arr, transform, nodata, dtype="float32"):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype, crs="EPSG:4326", transform=transform, nodata=nodata) as dst:
        dst.write(arr.astype(dtype), 1)


# ---- joiners --------------------------------------------------------------------------------


def test_block_mean_ignores_invalid_and_pads_edges():
    arr = np.arange(30, dtype="float64").reshape(5, 6)
    valid = np.ones((5, 6), dtype=bool)
    valid[0, 0] = False
    mean, ok = h3util.block_mean(arr, valid, 2)
    assert mean.shape == (3, 3) and ok.all()
    assert mean[0, 0] == pytest.approx((1 + 6 + 7) / 3)  # the invalid pixel is left out
    assert mean[2, 2] == pytest.approx((28 + 29) / 2)  # padded last row: two pixels only


def test_raster_mean_decimated_matches_full_resolution(tmp_path):
    """A constant-by-region raster gives the same hex means at 100 m and block-averaged to 1 km."""
    px = 0.002
    lng = np.arange(10 + px / 2, 12, px)
    lat = np.arange(43 - px / 2, 41, -px)
    LNG, LAT = np.meshgrid(lng, lat)
    arr = np.where(LNG < 11.0, 80.0, 20.0)
    arr[(LAT < 41.3)] = 255  # nodata strip
    path = tmp_path / "trees.tif"
    _write(path, arr, from_origin(10, 43, px, px), 255, dtype="uint8")
    cells = h3util.cells_for_geometry(box(10.2, 41.5, 11.8, 42.8), 5)
    hexes = pd.DataFrame({"h3": cells})
    full = raster_mean(hexes, path, 5, nodata=255)
    fast = raster_mean(hexes, path, 5, nodata=255, decimate=10)
    assert full.notna().all() and fast.notna().all()
    # a 1 km block straddling the 80/20 edge lands whole in one hex, so hexes on that edge may
    # differ by a few points; every hex must still be close and the interiors identical
    assert np.allclose(full.to_numpy(), fast.to_numpy(), atol=6.0)
    assert np.abs(full.to_numpy() - fast.to_numpy()).mean() < 1.0
    west = hexes["h3"].map(lambda c: h3.cell_to_latlng(c)[1] < 10.7)
    assert (full[west] > 75).all() and (full[~west & hexes["h3"].map(lambda c: h3.cell_to_latlng(c)[1] > 11.3)] < 25).all()


def test_raster_mean_centroid_sampling_and_missing(tmp_path):
    arr = np.array([[1.0, 2.0], [-9999.0, 4.0]])
    path = tmp_path / "coarse.tif"
    _write(path, arr, from_origin(10, 42, 1.0, 1.0), -9999.0)
    cells = [_cell(41.5, 10.5), _cell(41.5, 11.5), _cell(40.5, 10.5), _cell(45.0, 10.5)]
    out = raster_mean(pd.DataFrame({"h3": cells}), path, 4, sample="centroid")
    assert out.iloc[0] == 1.0 and out.iloc[1] == 2.0
    assert np.isnan(out.iloc[2]) and np.isnan(out.iloc[3])  # nodata and outside the raster


def test_point_mean_weights_by_tests_and_leaves_empty_hexes_nan():
    a, b = _cell(42.5, 13.0), _cell(43.0, 11.0)
    la, lo = h3.cell_to_latlng(a)
    pts = pd.DataFrame({"lat": [la, la, la, -95.0], "lng": [lo, lo, lo, 0.0], "d_mbps": [100.0, 300.0, np.nan, 1.0], "tests": [1, 3, 5, 9]})
    out = point_mean(pd.DataFrame({"h3": [a, b]}), pts, 4, "d_mbps", weight_field="tests")
    assert out.iloc[0] == pytest.approx((100 * 1 + 300 * 3) / 4)
    assert np.isnan(out.iloc[1])
    unweighted = point_mean(pd.DataFrame({"h3": [a]}), pts, 4, "d_mbps")
    assert unweighted.iloc[0] == pytest.approx(200.0)


# ---- prep -----------------------------------------------------------------------------------


def test_ookla_prepare_converts_kbps_and_drops_unusable_tiles():
    df = pd.DataFrame({"quadkey": ["a", "b", "c", "d"], "tile_x": [13.0, 13.1, 200.0, 13.2], "tile_y": [42.5, 42.6, 42.7, 42.8], "avg_d_kbps": [120000, 0, 50000, 80000], "tests": [10, 5, 3, 0]})
    out = ookla.prepare(df)
    assert list(out.columns) == ["lat", "lng", "d_mbps", "tests"]
    assert len(out) == 1 and out.loc[0, "d_mbps"] == 120.0 and out.loc[0, "lat"] == 42.5
    with pytest.raises(KeyError, match="tile_x"):
        ookla.prepare(df.drop(columns=["tile_x"]))


def test_aqueduct_prepare_turns_sentinel_into_nan():
    gdf = gpd.GeoDataFrame({"drr_cat": [3, -9999, 0], "other": [1, 2, 3]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)], crs=4326)
    out = aqueduct.prepare(gdf)
    assert list(out.columns) == ["drr_cat", "geometry"]
    assert out["drr_cat"].tolist()[0] == 3.0 and np.isnan(out["drr_cat"].iloc[1]) and out["drr_cat"].iloc[2] == 0.0


def test_pm25_geotiff_is_north_up_and_masks_non_positive(tmp_path):
    lat = np.array([40.005, 40.015, 40.025], dtype="float32")  # ascending, as the real file
    lon = np.array([10.005, 10.015], dtype="float32")
    pm = np.array([[1.0, -999.0], [2.0, 0.0], [3.0, 4.0]], dtype="float32")  # row 0 = southernmost
    nc = tmp_path / "pm.nc"
    xr.Dataset({"PM25": (("lat", "lon"), pm)}, coords={"lat": lat, "lon": lon}, attrs={"LAT_DELTA": 0.01, "LON_DELTA": 0.01}).to_netcdf(nc)
    out = rasters.pm25_geotiff(nc, tmp_path / "pm.tif", slab_rows=2)
    with rasterio.open(out) as src:
        arr = src.read(1)
        assert src.crs.to_epsg() == 4326 and src.transform.c == pytest.approx(10.0) and src.transform.f == pytest.approx(40.03)
        assert src.transform.a == pytest.approx(0.01) and src.transform.e == pytest.approx(-0.01)
    assert arr[0, 0] == 3.0 and arr[2, 0] == 1.0  # flipped to north-up
    assert not np.isnan(arr[0, 1]) and arr[0, 1] == 4.0
    assert np.isnan(arr[1, 1]) and np.isnan(arr[2, 1])  # 0.0 and the negative sentinel are missing


def test_gfed5_burned_fraction_from_monthly_km2(tmp_path):
    import zipfile

    lat = np.array([-0.125, 0.125])  # two 0.25 degree rows at the equator
    lon = np.array([0.125, 0.375])
    z = tmp_path / "BA.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for year in (2001, 2002):
            for month in (1, 7):
                total = np.zeros((1, 2, 2))
                total[0, 0, 0] = 100.0 if year == 2001 else 300.0  # cell (row0, col0) burns
                ds = xr.Dataset({"Total": (("time", "lat", "lon"), total), "Crop": (("time", "lat", "lon"), total * 0)}, coords={"time": [np.datetime64(f"{year}-{month:02d}-01")], "lat": lat, "lon": lon})
                nc = tmp_path / f"BA{year}{month:02d}.nc"
                ds.to_netcdf(nc)
                zf.write(nc, nc.name)
        zf.writestr("readme.html", "<p>km2</p>")
    out = rasters.gfed5_burned_fraction(z, tmp_path / "fire.tif", years=(2001, 2002), work_dir=tmp_path / "work")
    with rasterio.open(out) as src:
        arr = src.read(1)
        assert src.nodata == -9999.0 and src.transform.f == pytest.approx(0.25) and src.transform.c == pytest.approx(0.0)
    area = rasters._cell_area_km2(lat, 0.25, 0.25)[0, 0]  # ~773 km2 at the equator
    expected = 100.0 * ((200.0 / area) + (600.0 / area)) / 2  # two months per year, two years
    assert arr[1, 0] == pytest.approx(expected, rel=1e-6)  # north-up: lat 0.125 is row 0, -0.125 is row 1
    assert arr[0, 0] == 0.0 and arr[0, 1] == 0.0


# ---- dims on the fixture world -----------------------------------------------------------------


def test_extras_on_fixtures(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4).set_index("h3")
    inh = df[df["inhabited"]]
    for did in ("care", "air", "trees", "net", "fire", "drought"):
        tag = f"{did}_res"
        assert tag in df.columns and df[tag].isin(("hex", "basin", "none")).all()
        assert df.loc[df[tag] == "none", f"{did}_raw"].isna().all()  # invariant 3
    cedar, alder, dune = df.loc[_cell(42.5, 13.0)], df.loc[_cell(43.0, 11.0)], df.loc[_cell(43.6, 13.6)]
    # care: minutes grow with the distance to a town, so a hex between towns is worse than Cedar
    far = df.loc[_cell(41.7, 12.2)]
    assert cedar["care_res"] == "hex" and far["care_raw"] > cedar["care_raw"] > 0
    # air: PM2.5 peaks around Cedar, and the ocean-only hexes (negative sentinel) are missing
    assert cedar["air_raw"] > alder["air_raw"] and (inh["air_res"] == "hex").all()
    # trees: the north-west quadrant is forest (85), the rest 12; decimation must not blur that
    assert alder["trees_raw"] > 70 and 5 < cedar["trees_raw"] < 25 and cedar["trees_res"] == "hex"
    # net: fixed broadband around Cedar (first joiner), mobile only where fixed has no tiles (Dune)
    assert cedar["net_lbl"] == "fixed" and cedar["net_raw"] > 250
    assert dune["net_lbl"] == "mobile" and 30 < dune["net_raw"] < 55 and dune["net_res"] == "hex"
    assert df.loc[_cell(41.0, 10.5), "net_res"] == "none"  # nobody tests in the south-west
    # fire: 0.25 degree cells sampled at the centroid; the dry south-east burns 6%/yr, the wet north-west 0
    assert df.loc[_cell(40.7, 12.7), "fire_raw"] == pytest.approx(6.0) and alder["fire_raw"] == 0.0
    # drought: sub-basin category at the centroid, tagged basin; the desert sub-basin has no data
    assert df.loc[_cell(43.5, 13.0), "drought_raw"] == 4.0 and df.loc[_cell(43.5, 13.0), "drought_res"] == "basin"
    desert = df.loc[_cell(40.7, 12.5)]
    assert desert["drought_res"] == "none" and np.isnan(desert["drought_raw"])
