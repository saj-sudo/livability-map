"""The two global poverty / development loaders: World Bank GSAP (share above the $4.20 line) and
Global Data Lab SHDI. Both join a table to region polygons and are only ever run on real downloads,
so these tests build tiny stand-ins of the real layouts."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import openpyxl
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline.prep import gsap, shdi
from pipeline.registry import Source


def _src(sid, fmt, files, **extra) -> Source:
    return Source(id=sid, name="", group="life", access="manual", url="x", format=fmt, license="ok", files=list(files), extra=dict(extra))


def _regions(path, codes: list[str], code_col: str, crs=4326):
    boxes = [box(i, 0, i + 1, 1) for i in range(len(codes))]
    gpd.GeoDataFrame({code_col: codes}, geometry=boxes, crs=crs).to_file(path, driver="GPKG")


def _gsap_files(tmp_path, monkeypatch, settings, rows, region_codes, region_crs=4326):
    """A GSAP workbook (header on row 1, like the real sheet) and a region gpkg."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data 2023"
    ws.append(["code", "geo_code", "poor300_ln", "poor420_ln"])
    for r in rows:
        ws.append(list(r))
    (tmp_path / "wb_gsap").mkdir()
    wb.save(tmp_path / "wb_gsap" / "gsap.xlsx")
    (tmp_path / "wb_gsap_regions").mkdir()
    _regions(tmp_path / "wb_gsap_regions" / "regions.gpkg", region_codes, "geo_code", region_crs)
    monkeypatch.setattr(settings, "raw", lambda sid: tmp_path / sid)
    return _src("wb_gsap", "xlsx", ["gsap.xlsx"], sheet="Data 2023"), {"wb_gsap_regions": _src("wb_gsap_regions", "geopackage", ["regions.gpkg"])}


def test_gsap_turns_the_poverty_line_into_a_share_above_it(tmp_path, settings, monkeypatch):
    src, sources = _gsap_files(tmp_path, monkeypatch, settings, [("AAA", "AAA_1", 0.1, 0.25), ("AAA", "AAA_2", 0.0, 0.6)], ["AAA_1", "AAA_2"])
    out = gsap.load(settings, src, sources).set_index("geo_code")
    assert out.loc["AAA_1", "nonpoor_share"] == pytest.approx(0.75)
    assert out.loc["AAA_2", "nonpoor_share"] == pytest.approx(0.4)
    assert list(gsap.load(settings, src, sources).columns) == ["geo_code", "poor420_ln", "nonpoor_share", "geometry"]
    assert out.crs.to_epsg() == 4326


def test_gsap_clips_drops_empty_rows_and_duplicate_codes(tmp_path, settings, monkeypatch):
    rows = [
        ("A", "A_1", 0, 1.2),  # a poverty rate above 1 cannot give a negative share
        ("A", "A_2", 0, -0.1),  # nor can one below 0 give a share above 1
        ("A", "A_3", 0, None),  # no estimate: left out, never 0 or 1
        ("A", "A_3", 0, "n/a"),  # text is no estimate either
        ("A", "A_1", 0, 0.9),  # a repeated code keeps its first row
    ]
    src, sources = _gsap_files(tmp_path, monkeypatch, settings, rows, ["A_1", "A_2", "A_3"])
    out = gsap.load(settings, src, sources).set_index("geo_code")
    assert set(out.index) == {"A_1", "A_2"}  # A_3 had no estimate
    assert out.loc["A_1", "nonpoor_share"] == 0.0 and out.loc["A_2", "nonpoor_share"] == 1.0


def test_gsap_reprojects_regions_to_wgs84(tmp_path, settings, monkeypatch):
    src, sources = _gsap_files(tmp_path, monkeypatch, settings, [("A", "A_1", 0, 0.5)], ["A_1"], region_crs=3857)
    out = gsap.load(settings, src, sources)
    assert out.crs.to_epsg() == 4326 and out.total_bounds[2] < 1  # metres became degrees


def test_gsap_refuses_a_table_that_mostly_misses_the_polygons(tmp_path, settings, monkeypatch):
    rows = [("A", f"A_{i}", 0, 0.5) for i in range(10)]
    src, sources = _gsap_files(tmp_path, monkeypatch, settings, rows, ["A_0"])  # 1 of 10 rows has a polygon
    with pytest.raises(RuntimeError, match=r"only 10% of table rows found a polygon.*A_1"):
        gsap.load(settings, src, sources)


def test_gsap_names_the_missing_column(tmp_path, settings, monkeypatch):
    src, sources = _gsap_files(tmp_path, monkeypatch, settings, [("A", "A_1", 0, 0.5)], ["A_1"])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data 2023"
    ws.append(["code", "geo_code", "poor300_ln"])
    ws.append(["A", "A_1", 0.1])
    wb.save(tmp_path / "wb_gsap" / "gsap.xlsx")
    with pytest.raises(KeyError, match="poor420_ln"):
        gsap.load(settings, src, sources)


def _shdi_files(tmp_path, monkeypatch, settings, table: pd.DataFrame, region_codes: list[str], code_col="GDLcode"):
    (tmp_path / "gdl_shdi").mkdir()
    table.to_csv(tmp_path / "gdl_shdi" / "SHDI.csv", index=False)
    (tmp_path / "gdl_shdi_regions").mkdir()
    _regions(tmp_path / "gdl_shdi_regions" / "regions.gpkg", region_codes, code_col)
    monkeypatch.setattr(settings, "raw", lambda sid: tmp_path / sid)
    return _src("gdl_shdi_regions", "geopackage", ["regions.gpkg"]), {"gdl_shdi": _src("gdl_shdi", "csv", ["SHDI.csv"])}


def test_shdi_keeps_the_latest_year_of_each_subnational_region(tmp_path, settings, monkeypatch):
    table = pd.DataFrame(
        {
            "GDLCODE": ["AAAr101", "AAAr101", "AAAr102", "AAAt"],
            "level": ["Subnat", "Subnat", "Subnat", "National"],
            "year": [2018, 2022, 2019, 2022],
            "shdi": [0.60, 0.70, 0.55, 0.99],
        }
    )
    src, sources = _shdi_files(tmp_path, monkeypatch, settings, table, ["AAAr101", "AAAr102", "AAAt"])
    out = shdi.load(settings, src, sources).set_index("GDLCODE")
    assert out.loc["AAAr101", "shdi"] == 0.70 and out.loc["AAAr101", "year"] == 2022
    assert out.loc["AAAr102", "shdi"] == 0.55
    assert "AAAt" not in out.index  # national rows belong to the national fallback, not the region layer
    assert list(shdi.load(settings, src, sources).columns) == ["GDLCODE", "shdi", "year", "geometry"]


def test_shdi_drops_missing_values_and_unmatched_regions(tmp_path, settings, monkeypatch, capsys):
    table = pd.DataFrame({"gdlcode": ["R1", "R1", "R2", "R9"], "year": [2019, 2022, 2022, 2022], "SHDI": [0.5, np.nan, 0.6, 0.7]})
    src, sources = _shdi_files(tmp_path, monkeypatch, settings, table, ["R1", "R2", "R3"], code_col="GDLCODE")  # no `level` column, mixed-case names
    out = shdi.load(settings, src, sources).set_index("GDLCODE")
    assert out.loc["R1", "shdi"] == 0.5 and out.loc["R1", "year"] == 2019  # the 2022 value is missing, so 2019 is the latest real one
    assert set(out.index) == {"R1", "R2"}  # R3 has no value and R9 has no polygon
    assert "2 regions with SHDI out of 3 polygons / 3 table rows" in capsys.readouterr().out


def test_shdi_names_the_missing_column(tmp_path, settings, monkeypatch):
    table = pd.DataFrame({"GDLCODE": ["R1"], "year": [2022]})
    src, sources = _shdi_files(tmp_path, monkeypatch, settings, table, ["R1"], code_col="GDLCODE")
    with pytest.raises(KeyError, match="shdi"):
        shdi.load(settings, src, sources)
