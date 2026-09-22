from __future__ import annotations

import geopandas as gpd
import pytest

from pipeline import prep
from pipeline.registry import Source
from pipeline.stages import fetch


def test_fixture_layers_pass_through(settings):
    fetch.run(settings)
    regions = prep.load_layer(settings, "gdl_shdi_regions")
    assert isinstance(regions, gpd.GeoDataFrame) and {"GDLCODE", "shdi"} <= set(regions.columns)
    whr = prep.load_layer(settings, "whr_ladder")
    assert {"iso_a2", "ladder"} <= set(whr.columns)
    tracts = prep.load_layer(settings, "acs_summary")
    assert {"emp_rate_16_29", "pct_white", "ss_couples_per_1k", "income_entropy"} <= set(tracts.columns)
    assert (tracts[["pct_white", "pct_black", "pct_hisp", "pct_asian", "pct_other"]].sum(axis=1).round(6) == 100).all()


def test_unknown_source_and_missing_loader_are_plain_errors(settings):
    with pytest.raises(KeyError, match="unknown source"):
        prep.load_layer(settings, "nope")


def test_country_to_iso2_handles_whr_spellings():
    from pipeline.prep.util import country_to_iso2

    assert country_to_iso2("Türkiye") == "TR" and country_to_iso2("Congo (Kinshasa)") == "CD"
    assert country_to_iso2("Finland") == "FI" and country_to_iso2("Narnia") is None
    assert country_to_iso2("Kosovo") == "XK" and country_to_iso2("North Cyprus") is None


def test_normalize_name_strips_accents_and_generic_words():
    from pipeline.prep.util import normalize_name

    assert normalize_name("Région Île-de-France") == "ile de france"
    assert normalize_name("Provincia autónoma de Trento") == "provincia autonoma de trento"


def test_whr_loader_on_synthetic_xlsx(tmp_path, settings, monkeypatch):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Year", "Rank", "Country name", "Life evaluation (3-year average)", "Lower whisker"])
    ws.append([2024, 1, "Finland", 7.7, 7.6])
    ws.append([2025, 1, "Finland", 7.764, 7.69])
    ws.append([2025, 2, "Türkiye", 5.0, 4.9])
    ws.append([2025, 3, "North Cyprus", 5.5, 5.4])
    p = tmp_path / "WHR26_Data_Figure_2.1.xlsx"
    wb.save(p)
    from pipeline.prep import whr

    src = Source(id="whr_ladder", name="", group="wellbeing", access="direct", url="x", format="xlsx", license="ok", files=[p.name])
    monkeypatch.setattr(settings, "raw", lambda sid: tmp_path)
    df = whr.load(settings, src, {})
    assert df.set_index("iso_a2").loc["FI", "ladder"] == 7.764
    assert set(df["iso_a2"]) == {"FI", "TR"} and (df["year"] == 2025).all()
