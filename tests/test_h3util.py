from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from pipeline import h3util


@pytest.fixture()
def small_raster(tmp_path):
    """0.01 degree raster of ones over a 1x1 degree box, with a nodata hole."""
    arr = np.ones((100, 100), dtype="float32")
    arr[:10, :10] = -1
    path = tmp_path / "ones.tif"
    with rasterio.open(path, "w", driver="GTiff", height=100, width=100, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(10.0, 41.0, 0.01, 0.01), nodata=-1) as dst:
        dst.write(arr, 1)
    return path


def test_cells_for_geometry_matches_h3():
    cells = h3util.cells_for_geometry(box(10, 40, 11, 41), 4)
    assert len(cells) > 0
    assert all(len(c) == 15 for c in cells)


def test_aggregate_sum_conserves_total(small_raster):
    df = h3util.aggregate_raster(small_raster, 5, "sum", window_size=37)
    assert df["value"].sum() == pytest.approx(100 * 100 - 100)
    assert df["n_pixels"].sum() == 100 * 100
    assert (df["n_valid"] <= df["n_pixels"]).all()


def test_aggregate_mean_and_frac_above(small_raster):
    mean = h3util.aggregate_raster(small_raster, 5, "mean")
    assert np.allclose(mean["value"].dropna(), 1.0)
    frac = h3util.aggregate_raster(small_raster, 5, "frac_above", threshold=0.5)
    assert np.allclose(frac["value"].dropna(), 1.0)
    frac2 = h3util.aggregate_raster(small_raster, 5, "frac_above", threshold=2.0)
    assert np.allclose(frac2["value"].dropna(), 0.0)


def test_window_size_does_not_change_result(small_raster):
    a = h3util.aggregate_raster(small_raster, 5, "sum", window_size=1000).set_index("h3")["value"]
    b = h3util.aggregate_raster(small_raster, 5, "sum", window_size=23).set_index("h3")["value"]
    assert a.index.equals(b.index)
    assert np.allclose(a.to_numpy(), b.to_numpy())


def test_bbox_limits_work(small_raster):
    full = h3util.aggregate_raster(small_raster, 5, "sum")
    part = h3util.aggregate_raster(small_raster, 5, "sum", bbox=(10.0, 40.0, 10.3, 40.3))
    assert part["n_pixels"].sum() == pytest.approx(30 * 30)
    assert set(part["h3"]) <= set(full["h3"])


def test_sample_at_centroids(small_raster):
    cells = h3util.cells_for_geometry(box(10.2, 40.2, 10.8, 40.8), 5)
    s = h3util.sample_at_centroids(small_raster, cells)
    assert np.allclose(s.to_numpy(), 1.0)
