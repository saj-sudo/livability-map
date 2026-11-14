"""EU cities perception survey (prep/eu_qol.py) and Opportunity Atlas crosswalk (prep/opp_atlas.py)
loaders, plus their dimensions on the fixture world (SPEC §13.48)."""

from __future__ import annotations

from types import SimpleNamespace

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pytest
import shapely
from shapely.geometry import box

from pipeline import sanity
from pipeline.prep import eu_qol, opp_atlas
from pipeline.registry import Source

# ---- EU QoL survey ----------------------------------------------------------------------------

GAY = "My city is a good place to live for gay or lesbian people"
IMM = "My city is a good place to live for immigrants from other countries"
SAFE = "I feel safe walking alone at night in my city"
BUS = "Satisfied with public transport"


def _long(rows):
    return pd.DataFrame(rows, columns=["city_code", "question", "answer", "value"])


def test_agreement_sums_strongly_and_somewhat_and_ignores_other_rows():
    df = _long([
        ("DE001C", GAY, "Strongly agree", "40"), ("DE001C", GAY, "Somewhat agree", "30.5"),
        ("DE001C", GAY, "Somewhat disagree", "10"), ("DE001C", GAY, "Strongly disagree", "9"),
        ("DE001C", GAY, "Don't know / no answer", "10.5"),
        ("DE001C", IMM, "Strongly agree", "20"), ("DE001C", IMM, "Somewhat agree", "25"),
        ("DE001C", SAFE, "Strongly agree", "35"), ("DE001C", SAFE, "Somewhat agree", "30"),
        ("DE001C", BUS, "Strongly agree", "90"),  # another question: ignored
        ("FR001C", SAFE, "Strongly agree", "20"), ("FR001C", SAFE, "Somewhat agree", "35"),
    ])
    out = eu_qol.agreement(eu_qol.tidy(df)).set_index("city")
    assert out.loc["DE001C", "gay_good_pct"] == pytest.approx(70.5)
    assert out.loc["DE001C", "immig_good_pct"] == 45 and out.loc["DE001C", "safe_night_pct"] == 65
    assert out.loc["FR001C", "safe_night_pct"] == 55
    # Paris has no gay / immigrant rows: missing, never 0
    assert pd.isna(out.loc["FR001C", "gay_good_pct"]) and pd.isna(out.loc["FR001C", "immig_good_pct"])
    assert list(out.columns) == list(eu_qol.ITEMS)


def test_agreement_prefers_a_published_total_and_keeps_the_latest_year():
    df = pd.DataFrame({
        "cities": ["AT001C"] * 5,
        "indic_ur": [f"{GAY} - Strongly agree", f"{GAY} - Somewhat agree", f"{GAY} - Agree (total)", f"{GAY} - Strongly agree", f"{GAY} - Somewhat agree"],
        "TIME_PERIOD": ["2023", "2023", "2023", "2019", "2019"],
        "OBS_VALUE": ["40", "30", "71", "10", "10"],
    })
    out = eu_qol.agreement(eu_qol.tidy(df)).set_index("city")
    assert out.loc["AT001C", "gay_good_pct"] == 71  # the total row, from 2023 only


def test_eurostat_tsv_layout_with_flags_and_fractions():
    tsv = pd.DataFrame({
        "indic_ur,cities\\time": [f"{SAFE} - strongly agree,BE001C", f"{SAFE} - somewhat agree,BE001C", f"{SAFE} - strongly agree,ES001C", f"{SAFE} - somewhat agree,ES001C"],
        "2023 ": ["0.302 u", "0.40", ": ", "0.25"],
        "2019 ": ["0.1", "0.1", "0.1", "0.1"],
    })
    out = eu_qol.agreement(eu_qol.tidy(tsv)).set_index("city")
    assert out.loc["BE001C", "safe_night_pct"] == pytest.approx(70.2)  # fractions -> percent, flag stripped
    assert out.loc["ES001C", "safe_night_pct"] == pytest.approx(25.0)  # ":" is missing, the other part still counts


def test_item_codes_from_the_source_and_label_columns():
    df = pd.DataFrame({
        "cities": ["IT001C", "IT001C", "IT001C"],
        "indic_ur": ["PS1", "PS2", "PS9"],
        "indic_ur_label": ["Strongly agree", "Somewhat agree", "Strongly agree"],
        "OBS_VALUE": ["30", "20", "77"],
    })
    out = eu_qol.agreement(eu_qol.tidy(df), {"immig_good_pct": ["PS1", "PS2"]}).set_index("city")
    assert out.loc["IT001C", "immig_good_pct"] == 50 and pd.isna(out.loc["IT001C", "gay_good_pct"])
    with pytest.raises(KeyError, match="unknown item"):
        eu_qol.agreement(eu_qol.tidy(df), {"nonsense": ["PS1"]})


def test_survey_loader_errors_are_plain():
    with pytest.raises(KeyError, match="columns found"):
        eu_qol.tidy(pd.DataFrame({"town": ["X"], "pct": ["1"]}))
    with pytest.raises(ValueError, match="no row matched the three items"):
        eu_qol.agreement(eu_qol.tidy(_long([("DE001C", BUS, "Strongly agree", "90")])))


def test_city_codes_match_on_the_urau_stem_and_names_as_a_fallback(capsys):
    assert eu_qol.city_key("de001c1") == "DE001C" and eu_qol.city_key("Berlin") is None
    shares = pd.DataFrame({"city": ["DE001C1", "Wien", "TR099C"], "gay_good_pct": [70.0, 60.0, 20.0], "immig_good_pct": [50.0, np.nan, 30.0], "safe_night_pct": [65.0, 80.0, 40.0]})
    cities = gpd.GeoDataFrame({"URAU_CODE": ["DE001C", "AT001C", "FR001C"], "URAU_NAME": ["Berlin", "Wien", "Paris"]}, geometry=[box(13, 52, 14, 53), box(16, 48, 17, 49), box(2, 48, 3, 49)], crs=4326)
    out = eu_qol.attach(shares, cities).set_index("city_code")
    assert sorted(out.index) == ["AT001C", "DE001C"]  # Paris was not surveyed, TR099C has no polygon
    assert out.loc["DE001C", "gay_good_pct"] == 70 and pd.isna(out.loc["AT001C", "immig_good_pct"])
    assert "TR099C" in capsys.readouterr().out


def test_eu_qol_load_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    (raw / "eu_qol_cities").mkdir(parents=True)
    (raw / "gisco_urau_cities").mkdir(parents=True)
    pd.DataFrame({"URAU_CODE": ["NL001C", "NL002C"], "q": [GAY, SAFE], "a": ["Strongly agree", "Somewhat agree"], "Value": ["50", "60"]}).rename(columns={"q": "Question", "a": "Answer"}).to_csv(raw / "eu_qol_cities" / "s.csv", sep=";", index=False)
    gpd.GeoDataFrame({"URAU_CODE": ["NL001C", "NL002C"], "URAU_NAME": ["Den Haag", "Amsterdam"]}, geometry=[box(4, 52, 4.5, 52.2), box(4.7, 52.3, 5.0, 52.45)], crs=4326).to_file(raw / "gisco_urau_cities" / "c.geojson", driver="GeoJSON")
    settings = SimpleNamespace(raw=lambda sid: raw / sid)
    src = Source("eu_qol_cities", "s", "life", "manual", None, "csv", "CC BY 4.0", ["s.csv"], extra={"geometry": "gisco_urau_cities"})
    geom = Source("gisco_urau_cities", "c", "reference", "manual", None, "geojson", "x", ["c.geojson"])
    out = eu_qol.load(settings, src, {"gisco_urau_cities": geom}).set_index("city_code")
    assert out.crs.to_epsg() == 4326 and out.loc["NL001C", "gay_good_pct"] == 50 and out.loc["NL002C", "safe_night_pct"] == 60
    assert out["immig_good_pct"].isna().all()


# ---- Opportunity Atlas ------------------------------------------------------------------------


def test_atlas_prepare_builds_padded_geoids_and_drops_out_of_range():
    df = pd.DataFrame({
        "state": ["1", "6", "6", "6"], "county": ["1", "37", "37", "37"], "tract": ["20100", "101110", "101120", "101130"],
        "kfr_pooled_pooled_mean": ["0.41", "", "1.7", "0.5"], "kfr_pooled_pooled_p25": ["0.33", "", "", ""],
        "kfr_pooled_pooled_n": ["120", "5", "9", "40"], "kfr_black_pooled_mean": ["0.3", "0.3", "0.3", "0.3"],
    })
    out = opp_atlas.prepare(df).set_index("GEOID10")
    assert list(out.index) == ["01001020100", "06037101130"]  # rows with neither rank dropped; impossible ranks are missing, never 0
    assert out.loc["01001020100", "kfr"] == pytest.approx(0.41) and out.loc["01001020100", "kfr25"] == pytest.approx(0.33)
    assert out.loc["01001020100", "n"] == 120 and pd.isna(out.loc["06037101130", "kfr25"])  # one measure blank, the other kept
    one = opp_atlas.prepare(pd.DataFrame({"GEOID": ["6037101110"], "kfr_pooled_pooled_mean": ["0.5"], "kfr_pooled_pooled_p25": ["0.4"]}))
    assert one["GEOID10"].iloc[0] == "06037101110" and one["n"].isna().all()


def test_atlas_prepare_names_the_columns_it_found():
    # either measure missing stops with what the file has
    with pytest.raises(KeyError, match=r"missing 'kfr_pooled_pooled_mean'.*kfr_pooled_pooled_p25"):
        opp_atlas.prepare(pd.DataFrame({"state": ["1"], "county": ["1"], "tract": ["1"], "kfr_pooled_pooled_p25": ["0.4"]}))
    with pytest.raises(KeyError, match=r"missing 'kfr_pooled_pooled_p25'.*kfr_pooled_pooled_mean"):
        opp_atlas.prepare(pd.DataFrame({"state": ["1"], "county": ["1"], "tract": ["1"], "kfr_pooled_pooled_mean": ["0.4"]}))
    with pytest.raises(KeyError, match="state, county and tract"):
        opp_atlas.prepare(pd.DataFrame({"place": ["x"], "kfr_pooled_pooled_mean": ["0.4"], "kfr_pooled_pooled_p25": ["0.3"]}))
    with pytest.raises(KeyError, match="AREALAND_PART"):
        opp_atlas.read_relationship(pd.DataFrame({"GEOID_TRACT_20": ["1"], "GEOID_TRACT_10": ["1"]}))


def _rel(rows):
    raw = pd.DataFrame(rows, columns=["﻿GEOID_TRACT_20", "GEOID_TRACT_10", "AREALAND_PART", "AREAWATER_PART"]).astype(str)
    return opp_atlas.read_relationship(raw)


def test_crosswalk_weights_by_land_area_and_keeps_missing_missing():
    # D is suppressed in the Atlas (prepare() drops it); C has no 25th-percentile value
    values = pd.DataFrame({"GEOID10": ["A", "B", "C"], "kfr": [0.30, 0.40, 0.60], "kfr25": [0.25, 0.32, np.nan], "n": [100.0, 400.0, 100.0]})
    rel = _rel([
        ("T1", "A", 600, 0), ("T2", "A", 400, 0),  # A is split across two 2020 tracts
        ("T3", "B", 300, 0), ("T3", "C", 100, 0),  # T3 merges B and C
        ("T4", "D", 500, 0),  # only a suppressed parent
        ("T5", "B", 100, 0), ("T5", "D", 300, 0),  # valued parents cover a quarter of T5: missing
        ("T6", "C", 0, 50),  # water-only tract: total area weights
    ])
    out = opp_atlas.crosswalk(values, rel).set_index("GEOID")
    assert out.loc["T1", "kfr_pooled"] == pytest.approx(0.30) and out.loc["T2", "kfr_pooled"] == pytest.approx(0.30)
    assert out.loc["T3", "kfr_pooled"] == pytest.approx((0.4 * 300 + 0.6 * 100) / 400)
    assert "T4" not in out.index and "T5" not in out.index
    assert out.loc["T6", "kfr_pooled"] == pytest.approx(0.60)
    # each measure is crosswalked on its own: T3's p25 comes from B (3/4 of its land, enough), T6 has none
    assert out.loc["T1", "kfr_p25"] == pytest.approx(0.25) and out.loc["T3", "kfr_p25"] == pytest.approx(0.32)
    assert pd.isna(out.loc["T6", "kfr_p25"])
    # children apportioned by the overlap's share of each 2010 tract's land
    assert out.loc["T1", "children"] == pytest.approx(60) and out.loc["T2", "children"] == pytest.approx(40)
    assert out.loc["T3", "children"] == pytest.approx(400 * 300 / 400 + 100 * 100 / 100)


def test_crosswalk_without_child_counts_weights_hexes_by_land_area():
    values = pd.DataFrame({"GEOID10": ["A"], "kfr": [0.5], "kfr25": [0.4], "n": [np.nan]})
    out = opp_atlas.crosswalk(values, _rel([("T1", "A", 600, 0), ("T2", "A", 400, 0)])).set_index("GEOID")
    assert out.loc["T1", "children"] == 600 and out.loc["T2", "kfr_pooled"] == 0.5


def test_fixture_world_atlas_values_come_from_the_real_crosswalk(fixture_dir):
    atlas = opp_atlas.prepare(pd.read_csv(fixture_dir / "opp_tracts10.csv", dtype=str))
    rel = opp_atlas.read_relationship(opp_atlas.read_rel_file(fixture_dir / "tract_rel_2020_2010.txt"))
    assert rel.groupby("GEOID10")["GEOID"].nunique().max() == 2  # 2010 tracts split across two 2020 tracts
    table = opp_atlas.crosswalk(atlas, rel).set_index("GEOID")
    tracts = gpd.read_file(fixture_dir / "tracts.gpkg").set_index("GEOID")
    for col in ("kfr_pooled", "kfr_p25"):
        got = tracts[col].dropna()
        assert len(got) and np.allclose(got, table.loc[got.index, col].round(4)), col
        assert tracts[col].isna().any(), col  # suppressed (desert) 2010 tracts stay missing
    both = tracts.dropna(subset=["kfr_pooled", "kfr_p25"])
    assert len(both) and (both["kfr_p25"] < both["kfr_pooled"]).all()  # low-income kids rank lower, as in the real Atlas


def test_opp_atlas_load_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    for d in ("opp_atlas", "census_tract_rel_2020_2010", "cb_tracts"):
        (raw / d).mkdir(parents=True)
    pd.DataFrame({"state": [1], "county": [1], "tract": [20100], "kfr_pooled_pooled_mean": [0.42], "kfr_pooled_pooled_p25": [0.31], "kfr_white_male_mean": [0.5]}).to_csv(raw / "opp_atlas" / "a.csv", index=False)
    (raw / "census_tract_rel_2020_2010" / "r.txt").write_text(
        "﻿OID_TRACT_20|GEOID_TRACT_20|AREALAND_TRACT_20|GEOID_TRACT_10|AREALAND_TRACT_10|AREALAND_PART|AREAWATER_PART\n1|01001020101|50|01001020100|100|50|0\n2|01001020102|50|01001020100|100|50|0\n",
        encoding="utf-8",
    )
    gpd.GeoDataFrame({"GEOID": ["01001020101", "01001020102", "01001020200"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)], crs=4326).to_file(raw / "cb_tracts" / "t.geojson", driver="GeoJSON")
    settings = SimpleNamespace(raw=lambda sid: raw / sid)
    src = Source("opp_atlas", "a", "life", "manual", None, "csv", "x", ["a.csv"], extra={"geometry": "cb_tracts", "also_needs": ["census_tract_rel_2020_2010"]})
    sources = {
        "cb_tracts": Source("cb_tracts", "t", "life", "direct", "u", "geojson", "x", ["t.geojson"]),
        "census_tract_rel_2020_2010": Source("census_tract_rel_2020_2010", "r", "reference", "direct", "u", "txt-pipe", "x", ["r.txt"]),
    }
    out = opp_atlas.load(settings, src, sources).set_index("GEOID")
    assert sorted(out.index) == ["01001020101", "01001020102"]  # the third tract has no value: absent, never 0
    assert np.allclose(out["kfr_pooled"], 0.42) and np.allclose(out["kfr_p25"], 0.31) and (out["children"] == 50).all()  # no child count: land area


# ---- fixture-world dimensions -----------------------------------------------------------------


def _merged(settings):
    from pipeline.stages import admin, dims, fetch, grid, hazards, pop

    for stage in (fetch, grid, pop, admin, hazards, dims):
        stage.run(settings)
    return sanity.load_merged(settings, 4)


def test_eu_city_survey_dims_on_fixtures(settings):
    from pipeline.fixtures.make_fixtures import EU_CITIES

    df = _merged(settings)
    inside = shapely.contains_xy(shapely.union_all([box(*c[2]) for c in EU_CITIES]), df["lng"].to_numpy(), df["lat"].to_numpy())
    city, rest = df[inside], df[~inside]
    assert len(city) >= 3 and (city["iso_a2"] == "XA").all()
    for dim in ("lgbtq", "safe"):
        assert (city[f"{dim}_res"] == "city").all() and (city[f"{dim}_dom"] == "eucities").all() and (city[f"{dim}_lbl"] == "euqol").all()
    for dim in ("immig", "safe"):
        assert (rest[f"{dim}_res"] == "none").all() and rest[f"{dim}_raw"].isna().all()
    # Birch has no immigrants item: missing there, never 0, while its other two items are present
    birch = df.set_index("h3").loc[h3.latlng_to_cell(41.0, 11.5, 4)]
    assert birch["immig_res"] == "none" and pd.isna(birch["immig_raw"]) and birch["safe_raw"] == np.float32(74.0)
    alder = df.set_index("h3").loc[h3.latlng_to_cell(43.0, 11.0, 4)]
    assert alder["lgbtq_raw"] == np.float32(72.0) and alder["immig_raw"] == np.float32(61.0)


def test_lgbtq_keeps_acs_in_the_us_and_takes_the_city_survey_in_eu_cities(settings):
    df = _merged(settings)
    xa, xb = df[df["iso_a2"] == "XA"], df[df["iso_a2"] == "XB"]
    assert (xb.loc[xb["lgbtq_res"] != "none", "lgbtq_lbl"] == "acs").all() and (xb["lgbtq_res"] == "tract").any()
    assert set(xa["lgbtq_res"]) == {"city", "none"} and (xa.loc[xa["lgbtq_res"] == "city", "lgbtq_dom"] == "eucities").all()


def test_opp_and_opp25_are_us_only_on_fixtures(settings):
    df = _merged(settings)
    xa, xb = df[df["iso_a2"] == "XA"], df[df["iso_a2"] == "XB"]
    for dim in ("opp", "opp25"):
        assert (xa[f"{dim}_res"] == "none").all() and xa[f"{dim}_raw"].isna().all(), dim
        assert (xb[f"{dim}_res"] == "tract").any() and (xb.loc[xb[f"{dim}_res"] != "none", f"{dim}_dom"] == "us").all(), dim
    cedar = df.set_index("h3").loc[h3.latlng_to_cell(42.5, 13.0, 4)]
    assert cedar["opp_res"] == "tract" and cedar["opp_dom"] == "us" and 0.5 < cedar["opp_raw"] < 0.66
    assert cedar["opp25_res"] == "tract" and 0.3 < cedar["opp25_raw"] < cedar["opp_raw"]  # low-income kids rank lower
    assert xb["opp25_raw"].dropna().between(0.3, 0.5).all()
    assert (xb.loc[xb["opp_res"] != "none", "opp_dom"] == "us").all() and xb["opp_raw"].dropna().between(0.35, 0.66).all()
