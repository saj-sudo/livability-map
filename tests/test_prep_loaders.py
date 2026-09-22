"""Unit tests for the pure parts of the real-data loaders (synthetic inputs, no downloads)."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline.prep import acs, epa_sld, hrsa, ilostat, medsl, oecd, urban_edu


def test_ilostat_prepare_keeps_latest_total_youth_row():
    df = pd.DataFrame(
        {
            "ref_area": ["FRA", "FRA", "FRA", "FRA", "DEU", "XKX"],
            "sex": ["SEX_T", "SEX_T", "SEX_M", "SEX_T", "SEX_T", "SEX_T"],
            "classif1": ["AGE_YTHADULT_Y15-24", "AGE_YTHADULT_Y15-24", "AGE_YTHADULT_Y15-24", "AGE_YTHADULT_YGE15", "AGE_YTHADULT_Y15-24", "AGE_YTHADULT_Y15-24"],
            "time": [2022, 2024, 2024, 2024, 2030, 2023],
            "obs_value": [18.0, 17.5, 20.0, 7.0, 5.0, 40.0],
        }
    )
    out = ilostat.prepare(df, this_year=2026).set_index("iso_a2")
    assert out.loc["FR", "youth_employment_rate"] == 82.5 and out.loc["FR", "year"] == 2024
    assert "DE" not in out.index  # 2030 is a projection beyond this year
    assert out.loc["XK", "youth_employment_rate"] == 60.0


def test_oecd_crosswalk_matches_and_dissolves():
    corr = pd.DataFrame(
        [
            ("FRA", "FR10", 2, "FRA", "Île-de-France", "Île-de-France", "Ile-de-France"),
            ("FRA", "FRB", 2, "FRA", "Centre-Val de Loire", "Centre-Val de Loire", "Centre"),
            ("FRA", "FRZZ", 2, "FRA", "Atlantis", "Atlantis", "Atlantis"),
            ("JPN", "JPB", 2, "JPN", "Kanto region", "関東", "Kanto"),
            ("JPN", "JPB01", 3, "JPB", "Tokyo", "東京都", "Tokyo"),
            ("JPN", "JPB02", 3, "JPB", "Kanagawa", "神奈川県", "Kanagawa"),
            ("JPN", "JPC", 2, "JPN", "Kansai region", "関西", "Kansai"),
            ("JPN", "JPC01", 3, "JPC", "Osaka", "大阪府", "Osaka"),
        ],
        columns=["ISO3", "REG_ID", "TL", "PARENT", "NAME_ENG", "NAME_ORIG", "NAME_PUB"],
    )
    adm1 = gpd.GeoDataFrame(
        {"shapeGroup": ["FRA", "FRA", "JPN", "JPN", "JPN"], "shapeName": ["Ile-de-France", "Centre-Val de Loire", "Tokyo", "Kanagawa", "Osaka"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(10, 0, 11, 1), box(11, 0, 12, 1), box(12, 0, 13, 1)],
        crs=4326,
    )
    gdf, report = oecd.build_tl2_geometry(corr, adm1)
    assert set(gdf["Code"]) == {"FR10", "FRB", "JPB", "JPC"}
    assert report["FRA"]["method"] == "tl2" and report["FRA"]["unmatched"] == ["FRZZ"]
    assert report["JPN"]["method"] == "tl3" and report["JPN"]["matched"] == 2
    assert gdf.set_index("Code").loc["JPB", "geometry"].area == pytest.approx(2.0)


def test_oecd_overrides_win():
    corr = pd.DataFrame([("XXA", "XX1", 2, "XXA", "Northland", "Northland", "Northland")], columns=["ISO3", "REG_ID", "TL", "PARENT", "NAME_ENG", "NAME_ORIG", "NAME_PUB"])
    adm1 = gpd.GeoDataFrame({"shapeGroup": ["XXA", "XXA"], "shapeName": ["Alpha", "Beta"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=4326)
    overrides = pd.DataFrame({"tl2_code": ["XX1", "XX1"], "iso3": ["XXA", "XXA"], "shape_name": ["Alpha", "Beta"]})
    gdf, report = oecd.build_tl2_geometry(corr, adm1, overrides)
    assert len(gdf) == 1 and gdf.iloc[0]["geometry"].area == pytest.approx(2.0) and report["XXA"]["matched"] == 1


def test_acs_derive_fields():
    idx = pd.Index(["1400000US01001020100"], name="GEO_ID")

    def t(d):
        return pd.DataFrame(d, index=idx)

    b23 = {f"B23001_{c}": [0.0] for band in acs.B23001_BANDS.values() for c in band}
    # male 16-19: total 100, employed 60, unemployed 20; female 25-29: total 200, employed 150, unemployed 10
    b23.update({"B23001_003": [100.0], "B23001_007": [60.0], "B23001_008": [20.0], "B23001_110": [200.0], "B23001_114": [150.0], "B23001_115": [10.0]})
    tables = {
        "B23001": t(b23),
        "B03002": t({"B03002_001": [1000.0], "B03002_003": [500.0], "B03002_004": [200.0], "B03002_006": [50.0], "B03002_007": [10.0], "B03002_012": [150.0]}),
        "B19001": t({"B19001_001": [160.0], **{f"B19001_{c}": [10.0] for c in acs.INCOME_BRACKETS}}),
        "B19083": t({"B19083_001": [0.45]}),
        "B09019": t({"B09019_011": [4.0], "B09019_013": [6.0]}),
        "B11001": t({"B11001_001": [400.0]}),
        "B25003": t({"B25003_003": [120.0]}),
        "B25071": t({"B25071_001": [31.5]}),
    }
    out = acs.derive(tables).iloc[0]
    assert out["pop_16_29"] == 300 and out["emp_rate_16_29"] == pytest.approx(210 / 240)
    assert out["pct_white"] == 50 and out["pct_black"] == 20 and out["pct_hisp"] == 15 and out["pct_asian"] == 6
    assert out["pct_other"] == pytest.approx(9)
    assert out["ss_couples_per_1k"] == 25 and out["income_entropy"] == pytest.approx(1.0) and out["gini"] == 0.45
    assert out["rent_share_income"] == 31.5 and out["renter_households"] == 120 and out["households"] == 400


def test_acs_read_table_keeps_prefix_and_coerces_missing(tmp_path):
    p = tmp_path / "acsdt5y2024-b19083.dat"
    p.write_text("GEO_ID|B19083_E001|B19083_M001\n0100000US|0.48|0.001\n1400000US48201100001|0.51|0.02\n1400000US48201100002|-|**\n", encoding="utf-8")
    df = acs.read_table(p, ["B19083_001"])
    assert list(df.index) == ["1400000US48201100001", "1400000US48201100002"]
    assert df["B19083_001"].tolist()[0] == 0.51 and pd.isna(df["B19083_001"].iloc[1])


def test_acs_assert_labels_detects_renumbering():
    shells = dict(acs.EXPECTED_LABELS)
    acs.assert_labels(shells)
    shells["B23001_088"] = "Male:"
    with pytest.raises(RuntimeError, match="B23001_088"):
        acs.assert_labels(shells)


def test_medsl_total_mode_preferred_over_summing_modes():
    rows = [
        ("ALABAMA", 2024, "1001", "US PRESIDENT", "DEMOCRAT", 100, "TOTAL"),
        ("ALABAMA", 2024, "1001", "US PRESIDENT", "REPUBLICAN", 300, "TOTAL"),
        ("ALABAMA", 2024, "1001", "US PRESIDENT", "DEMOCRAT", 999, "EARLY VOTE"),  # ignored: TOTAL rows exist
        ("CALIFORNIA", 2024, "6037", "US PRESIDENT", "DEMOCRAT", 60, "ELECTION DAY"),
        ("CALIFORNIA", 2024, "6037", "US PRESIDENT", "DEMOCRAT", 40, "MAIL"),
        ("CALIFORNIA", 2024, "6037", "US PRESIDENT", "REPUBLICAN", 50, "ELECTION DAY"),
        ("CALIFORNIA", 2024, "6037", "US PRESIDENT", "OTHER", 10, "ELECTION DAY"),
        ("CALIFORNIA", 2020, "6037", "US PRESIDENT", "DEMOCRAT", 1000, "TOTAL"),
    ]
    df = pd.DataFrame(rows, columns=["state", "year", "county_fips", "office", "party", "candidatevotes", "mode"])
    out = medsl.prepare(df).set_index("GEOID")
    assert out.loc["01001", "margin_2024"] == -50
    assert out.loc["06037", "margin_2024"] == pytest.approx(100 * (100 - 50) / 150)
    assert out.loc["06037", "totalvotes"] == 160


def test_epa_sld_sentinel_becomes_nan():
    df = pd.DataFrame({"GEOID20": ["a", "b"], "D4C": [-99999, 12.5], "NatWalkInd": [5, 9], "TotPop": [100, 200]})
    out = epa_sld.prepare(df)
    assert pd.isna(out["D4C"][0]) and out["D4C"][1] == 12.5


def test_urban_all_students_filter():
    df = pd.DataFrame({"leaid": ["100005", "100005"], "race": [99, 1], "lep": [99, 99], "homeless": [99, 99], "disability": [99, 99], "econ_disadvantaged": [99, 99], "foster_care": [99, 99], "cohort_num": [500, 20], "grad_rate_midpt": [88.5, 70.0]})
    out = urban_edu.prepare(df)
    assert len(out) == 1 and out.loc[0, "LEAID"] == "0100005" and out.loc[0, "grad_rate_midpt"] == 88.5


def test_hrsa_per_10k_uses_newest_physician_column():
    ahrf = pd.DataFrame({"fips_st_cnty": ["1001", "1003"], "md_nf_activ_22": ["10", "20"], "md_nf_activ_23": ["12", "30"]})
    pop = pd.DataFrame({"GEOID": ["01001", "01003"], "county_pop": [60000.0, 0.0]})
    out = hrsa.prepare(ahrf, pop)
    assert len(out) == 1 and out.loc[0, "GEOID"] == "01001" and out.loc[0, "physicians_per_10k"] == pytest.approx(2.0)
