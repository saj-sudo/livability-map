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


def test_wpdx_loader_scores_water_present_and_drops_duplicates_and_unknowns(tmp_path):
    from pipeline.prep.wpdx import load_csv

    text = (
        "#lat_deg,#lon_deg,#status_id,is_duplicate,#clean_country_id\n"
        "-6.8,39.2,Yes,False,TZA\n"
        "-6.9,39.3,No,False,TZA\n"
        "-7.0,39.4,Unknown,False,TZA\n"
        "-7.1,39.5,Yes,True,TZA\n"
    )
    path = tmp_path / "wpdx.csv"
    path.write_text(text, encoding="utf-8")
    out = load_csv(path)
    assert list(out.columns) == ["lat", "lng", "has_water"]
    assert out["has_water"].tolist() == [1.0, 0.0]  # Unknown -> dropped, duplicate -> dropped


def _ct_zip(path, members: dict[str, str]):
    with zipfile.ZipFile(path, "w") as z:
        for name, text in members.items():
            z.writestr(name, text)
    return path


def test_climate_trace_loader_counts_each_allowed_asset_once(tmp_path):
    """§13.46: one point per asset (rows per gas and year collapse), allowed subsectors only,
    no point without coordinates, either coordinate spelling."""
    from pipeline.prep.climate_trace import load_zip

    power = (
        "source_id,source_name,subsector,lat,lon,gas,start_time,emissions_quantity\n"
        "1,Plant A,electricity-generation,10.0,20.0,co2,2023-01-01,5\n"
        "1,Plant A,electricity-generation,10.0,20.0,ch4,2023-01-01,1\n"
        "1,Plant A,electricity-generation,10.0,20.0,co2,2024-01-01,6\n"
        "2,Plant B,electricity-generation,,,co2,2024-01-01,3\n"
    )
    oil = (
        "source_id,subsector,latitude,longitude,gas\n"
        "7,oil-and-gas-refining,11.0,21.0,co2\n"
        "8,oil-and-gas-production-and-transport,12.0,22.0,co2\n"
    )
    path = _ct_zip(tmp_path / "power.zip", {"DATA/power/electricity-generation_emissions_sources_v4_5.csv": power, "DATA/fossil/oil-and-gas-refining_emissions_sources.csv": oil, "README.txt": "x"})
    out = load_zip(path, ["electricity-generation", "oil-and-gas-refining"])
    assert list(out.columns) == ["lat", "lng", "one"]
    assert sorted(zip(out["lat"], out["lng"], strict=True)) == [(10.0, 20.0), (11.0, 21.0)]
    assert (out["one"] == 1.0).all()


def test_climate_trace_loader_says_which_columns_it_found(tmp_path):
    from pipeline.prep.climate_trace import load_zip

    path = _ct_zip(tmp_path / "waste.zip", {"waste_emissions_sources.csv": "source_id,subsector,x,y\n1,solid-waste-disposal,1,2\n"})
    with pytest.raises(ValueError, match="no latitude column.*found"):
        load_zip(path, ["solid-waste-disposal"])
    empty = _ct_zip(tmp_path / "empty.zip", {"readme.txt": "x"})
    with pytest.raises(ValueError, match="no \\*emissions_sources\\*.csv member"):
        load_zip(empty, ["solid-waste-disposal"])


# ---- §13.49: GEM plants merged into industry, Overture amenities -----------------------------


def test_gem_keeps_operating_plants_once_and_merges_beside_climate_trace(tmp_path):
    import pandas as pd

    from pipeline.prep import gem

    df = pd.DataFrame(
        {
            "Plant name": ["A", "A", "B", "C", "D"],
            "Latitude": [10.0, 10.0, 11.0, 12.0, None],
            "Longitude": [20.0, 20.0, 21.0, 22.0, 23.0],
            "Status": ["operating", "Operating", "retired", "operating", "operating"],
        }
    )
    pts = gem.points_from_frame(df)
    assert sorted(zip(pts["lat"], pts["lng"], strict=True)) == [(10.0, 20.0), (12.0, 22.0)]  # units of A once; B retired; D no coordinates
    path = tmp_path / "gem_coal_plants.xlsx"
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame({"About": ["readme"]}).to_excel(xw, sheet_name="About", index=False)
        df.to_excel(xw, sheet_name="Units", index=False)
    assert len(gem.load_workbook(path)) == 2
    base = pd.DataFrame({"lat": [10.005], "lng": [20.0], "one": [1.0]})  # ~0.6 km from plant A
    merged = gem.merge(base, pts)
    assert len(merged) == 2 and (merged["one"] == 1.0).all()  # A is the same facility; C is new
    with pytest.raises(ValueError, match="no latitude/longitude"):
        gem.points_from_frame(pd.DataFrame({"x": [1]}))


def test_climate_trace_loader_adds_gem_plants_only_when_present(settings):
    from pipeline import prep
    from pipeline.prep.climate_trace import load
    from pipeline.registry import Source

    ct = Source(id="climate_trace_assets", name="", group="env", access="manual", url=None, format="csv-zip", license="CC BY 4.0", files=["power.zip"], extra={"subsectors": ["electricity-generation"], "also_uses": ["gem_trackers"]})
    gm = Source(id="gem_trackers", name="", group="env", access="manual", url=None, format="xlsx", license="CC BY 4.0", files=["gem_coal_plants.xlsx", "gem_steel_plants.xlsx"])
    sources = {ct.id: ct, gm.id: gm}
    raw = settings.raw(ct.id)
    raw.mkdir(parents=True, exist_ok=True)
    _ct_zip(raw / "power.zip", {"power_emissions_sources.csv": "source_id,subsector,lat,lon\n1,electricity-generation,10,20\n"})
    assert len(load(settings, ct, sources)) == 1
    assert prep.raw_inputs(settings, ct, sources) == [raw / "power.zip"]  # an absent optional file is not an input
    import pandas as pd

    settings.raw(gm.id).mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Latitude": [30.0], "Longitude": [40.0], "Status": ["operating"]}).to_excel(settings.raw(gm.id) / "gem_coal_plants.xlsx", index=False)
    assert len(load(settings, ct, sources)) == 2
    assert settings.raw(gm.id) / "gem_coal_plants.xlsx" in prep.raw_inputs(settings, ct, sources)


def test_overture_extract_filters_categories_and_confidence():
    from pathlib import Path

    import pandas as pd

    from pipeline.prep.overture_places import extract_sql, load_frame

    df = pd.DataFrame(
        {
            "lat": [1.0, 2.0, 3.0, 4.0, None],
            "lng": [1.0, 2.0, 3.0, 4.0, 5.0],
            "category": ["supermarket", "Pharmacy", "nightclub", "park", "park"],
            "confidence": [0.9, 0.7, 0.9, 0.3, 0.9],
        }
    )
    out = load_frame(df, ["supermarket", "pharmacy", "park"], min_confidence=0.6)
    assert list(out.columns) == ["lat", "lng", "one"] and out["lat"].tolist() == [1.0, 2.0]
    with pytest.raises(ValueError, match="lacks"):
        load_frame(df.drop(columns=["category"]), ["park"])
    sql = extract_sql("2026-10-15.0", ["park", "o'brien"], 0.6, Path("/tmp/x.parquet"), "basic_category")
    assert "release/2026-10-15.0/theme=places" in sql and "basic_category IN ('park', 'o''brien')" in sql and "confidence >= 0.6" in sql
