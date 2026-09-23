"""NGO source loaders added after Session 8 (SPEC §13.36)."""

from __future__ import annotations

import io
import zipfile

import pytest


def test_rwi_loader_renames_the_tile_centres():
    from pipeline.prep.meta_rwi import load_csv

    text = "quadkey,latitude,longitude,rwi,error\n3002302110302,-6.79,39.21,0.52,0.3\n30023021103021,-6.8,39.2,-1.1,0.4\n"
    out = load_csv(io.StringIO(text))
    assert list(out.columns) == ["lat", "lng", "rwi", "error"]
    assert out["rwi"].tolist() == [0.52, -1.1]


def test_ged_loader_keeps_recent_precisely_located_events_as_deaths_per_year(tmp_path):
    from pipeline.prep.ucdp_ged import YEARS, load_zip

    rows = [
        # year, where_prec, best, lat, lng
        (2024, 1, 20, -1.0, 36.0),
        (2019, 3, 5, -1.1, 36.1),
        (2024, 4, 100, -1.2, 36.2),  # located only to an admin1 centroid: dropped
        (2010, 1, 50, -1.3, 36.3),  # older than the window: dropped
        (2025, 2, 0, -1.4, 36.4),  # an event with no deaths stays (value 0)
    ]
    csv = "id,year,where_prec,best,latitude,longitude,type_of_violence\n" + "".join(f"{i},{y},{p},{b},{la},{lo},1\n" for i, (y, p, b, la, lo) in enumerate(rows))
    path = tmp_path / "ged.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("GEDEvent_v26_1.csv", csv)
    out = load_zip(path, "GEDEvent_v26_1.csv")
    assert len(out) == 3
    assert out["fatal_per_year"].tolist() == pytest.approx([20 / len(YEARS), 5 / len(YEARS), 0.0])
    assert list(out.columns) == ["lat", "lng", "fatal_per_year"]
