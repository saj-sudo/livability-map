"""``urban`` stage (SPEC §13.31): GHS-SMOD classes -> urban centre / cluster polygons with ids."""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point

from pipeline.stages import fetch, urban


def test_urban_polygons_cover_the_towns(settings):
    fetch.run(settings)
    counts = urban.run(settings)
    gdf = gpd.read_parquet(settings.urban_path)
    centres = gdf[gdf["kind"] == "centre"]
    assert counts["centre"] == len(centres) == 3  # Alder, Birch, Cedar
    assert centres["uc_id"].tolist() == [1, 2, 3] and centres["area_km2"].is_monotonic_decreasing
    assert centres.contains(Point(11.0, 43.0)).any()  # Alder
    assert not centres.contains(Point(12.5, 40.7)).any()  # desert
    clusters = gdf[gdf["kind"] == "cluster"]
    assert len(clusters) == 4 and clusters.contains(Point(13.6, 43.6)).any()  # Dune is a cluster only
    assert gdf.crs.to_epsg() == 4326


def test_pieces_split_across_windows_are_one_polygon(settings):
    fetch.run(settings)
    path = settings.raw("ghsl_smod") / "smod.tif"
    small = urban.polygons_from_raster(path, window_size=64)  # Cedar (radius ~9 px) crosses window edges
    big = urban.polygons_from_raster(path, window_size=2048)
    assert len(small) == len(big)
    assert abs(small["area_km2"].sum() - big["area_km2"].sum()) < 1e-6


def test_urban_is_cached(settings, capsys):
    fetch.run(settings)
    urban.run(settings)
    capsys.readouterr()
    urban.run(settings)
    assert "up to date" in capsys.readouterr().out


def test_pieces_merge_across_seams_on_a_non_round_grid(tmp_path):
    # final review I3: the real GHS-SMOD origin (-180.0079...) and 30 arc-second pixels make
    # window_transform edges differ by an ulp between neighbouring windows
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    arr = np.full((300, 300), 11, dtype="int16")
    arr[40:260, 40:260] = 30  # one big centre crossing several 64-pixel seams
    path = tmp_path / "smod.tif"
    t = from_origin(-180.00791593130032, 89.10012949387116, 0.008333333333333333, 0.008333333333333333)
    with rasterio.open(path, "w", driver="GTiff", height=300, width=300, count=1, dtype="int16", crs="EPSG:4326", transform=t, nodata=-200, tiled=True, blockxsize=64, blockysize=64) as dst:
        dst.write(arr, 1)
    for size in (64, 37):
        gdf = urban.polygons_from_raster(path, window_size=size)
        assert (gdf["kind"] == "centre").sum() == 1, size
