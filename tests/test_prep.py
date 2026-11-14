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

    assert normalize_name("Région Île-de-France") == "ile france"
    assert normalize_name("Provincia autónoma de Trento") == "trento"
    assert normalize_name("RegiÃ³n de AntofagastaÂ ") == "antofagasta"  # mojibake repaired


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


def test_editing_a_sources_yaml_key_reruns_the_loader(settings, monkeypatch):
    """§13.45: the prep cache key carries the source's own entry, so changing `sheet:` re-runs the
    loader instead of returning the layer prepared from the old sheet."""
    import pandas as pd

    import pipeline.prep.util as util

    calls: list[str] = []

    def toy(settings, source, sources):
        calls.append(source.extra["sheet"])
        return pd.DataFrame({"sheet": [source.extra["sheet"]]})

    monkeypatch.setattr(util, "toy_loader", toy, raising=False)
    monkeypatch.setitem(prep.LOADERS, "toy", "pipeline.prep.util:toy_loader")
    raw = settings.raw("toy")
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "toy.xlsx").write_bytes(b"x")

    def src(sheet: str, verified: str = "search") -> dict[str, Source]:
        return {"toy": Source(id="toy", name="t", group="life", access="manual", url=None, format="xlsx", license="CC BY 4.0", files=["toy.xlsx"], extra={"sheet": sheet, "verified": verified})}

    assert prep.load_layer(settings, "toy", src("A"))["sheet"].iloc[0] == "A"
    assert prep.load_layer(settings, "toy", src("A"))["sheet"].iloc[0] == "A"  # cached
    assert prep.load_layer(settings, "toy", src("A", verified="confirmed"))["sheet"].iloc[0] == "A"  # display-only key
    assert prep.load_layer(settings, "toy", src("B"))["sheet"].iloc[0] == "B"
    assert calls == ["A", "B"]
