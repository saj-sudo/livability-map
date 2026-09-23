"""Unit tests for the pure parts of the real-data loaders (synthetic inputs, no downloads)."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline.prep import acs, bea, epa_sld, hrsa, hud, icp, ilostat, medsl, oecd, urban_edu


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
    df = pd.DataFrame({"leaid": ["100005", "100005", "100006"], "race": [99, 1, 99], "lep": [99, 99, 99], "homeless": [99, 99, 99], "disability": [99, 99, 99], "econ_disadvantaged": [99, 99, 99], "foster_care": [99, 99, 99], "cohort_num": [500, 20, 30], "grad_rate_midpt": [88.5, 70.0, -3.0]})
    out = urban_edu.prepare(df)
    assert len(out) == 1 and out.loc[0, "LEAID"] == "0100005" and out.loc[0, "grad_rate_midpt"] == 88.5  # -3 is a suppression code


def test_hrsa_per_10k_uses_newest_physician_column():
    ahrf = pd.DataFrame({"fips_st_cnty": ["1001", "1003"], "md_nf_activ_22": ["10", "20"], "md_nf_activ_23": ["12", "30"]})
    pop = pd.DataFrame({"GEOID": ["01001", "01003"], "county_pop": [60000.0, 0.0]})
    out = hrsa.prepare(ahrf, pop)
    assert len(out) == 1 and out.loc[0, "GEOID"] == "01001" and out.loc[0, "physicians_per_10k"] == pytest.approx(2.0)


# ---- BEA regional price parities (cost) ---------------------------------------------------

BEA_COLUMNS = ["GeoFIPS", "GeoName", "Region", "TableName", "LineCode", "IndustryClassification", "Description", "Unit", "2022", "2023", "2024"]


def _bea_row(fips, name, line, v22, v23, v24):
    # GeoFIPS arrives from the CSV as BEA writes it: quoted and space-padded (' "01000"')
    return [f' "{fips}"', name, "5", "SARPP", line, "...", "RPPs: All items" if line == "1" else "RPPs: Goods", "Index", v22, v23, v24]


def test_bea_state_prepare_pads_geofips_and_keeps_all_items_latest_year():
    rows = [
        _bea_row("00000", "United States", "1", "100.000", "100.000", "100.000"),  # national row: no polygon
        _bea_row("01000", "Alabama", "1", "87.1", "87.5", "87.9"),
        _bea_row("01000", "Alabama", "2", "90.0", "90.2", "90.4"),  # goods line, ignored
        _bea_row("06000", "California", "1", "112.0", "112.3", "112.6"),
        _bea_row("72000", "Puerto Rico", "1", "(NA)", "(NA)", "(NA)"),  # missing stays missing, never 0
    ]
    out = bea.prepare(pd.DataFrame(rows, columns=BEA_COLUMNS), level="state").set_index("GEOID")
    assert list(out.index) == ["01", "06"]
    assert out.loc["01", "rpp_all"] == pytest.approx(87.9) and out.loc["06", "rpp_all"] == pytest.approx(112.6)
    assert (out["year"] == 2024).all()


def test_bea_metro_prepare_keeps_five_digit_cbsa_codes_only():
    rows = [
        _bea_row("00998", "United States (Metropolitan Portion)", "1", "101.0", "101.1", "101.2"),  # not a CBSA
        _bea_row("10180", "Abilene, TX (Metropolitan Statistical Area)", "1", "90.1", "90.3", "90.5"),
        _bea_row("35620", "New York-Newark-Jersey City, NY-NJ", "1", "118.0", "118.5", "119.0"),
    ]
    out = bea.prepare(pd.DataFrame(rows, columns=BEA_COLUMNS), level="metro").set_index("GEOID")
    assert list(out.index) == ["10180", "35620"] and out.loc["35620", "rpp_all"] == pytest.approx(119.0)


def test_bea_read_zip_member_drops_the_footer_lines(tmp_path):
    import zipfile

    text = (
        "GeoFIPS,GeoName,Region,TableName,LineCode,IndustryClassification,Description,Unit,2023,2024\n"
        '" 01000","Alabama",5,SARPP,1,...,"RPPs: All items",Index,87.5,87.9\n'
        '" 06000","California",8,SARPP,1,...,"RPPs: All items",Index,112.3,112.6\n'
        "\n"
        "Note: See the included footnote file.\n"
        "Legend / Footnotes:\n"
        "(NA) Not available.\n"
        "Last updated: February 19, 2026 -- new statistics for 2024.\n"
    )
    archive = tmp_path / "SARPP.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("SARPP_STATE_2008_2024.csv", text)
    df = bea.read_zip_member(archive, "SARPP_STATE_2008_2024.csv")
    assert len(df) == 2 and df["GeoFIPS"].str.strip().tolist() == ["01000", "06000"]
    out = bea.prepare(df, level="state")
    assert out["rpp_all"].tolist() == pytest.approx([87.9, 112.6])


# ---- World Bank ICP household price level and the WDI GDP fallback (cost) --------------------


def _icp_row(iso3, year, value):
    # one record of the ICP API's JSON (source 90, series 9100000, classification PX.WL)
    return {
        "variable": [
            {"concept": "Country", "id": iso3, "value": iso3},
            {"concept": "Time", "id": f"YR{year}", "value": str(year)},
            {"concept": "Series", "id": "9100000", "value": "9100000:HOUSEHOLDS AND NPISHS FINAL CONSUMPTION EXPENDITURE"},
            {"concept": "Classification", "id": "PX.WL", "value": "Price level index (World = 100)"},
        ],
        "value": value,
    }


def test_icp_parse_json_and_latest_non_null_year_per_country():
    payload = {"page": 1, "pages": 1, "source": {"id": "90", "name": "ICP 2021", "data": [_icp_row("FRA", 2020, 108.0), _icp_row("FRA", 2021, 110.0), _icp_row("FRA", 2022, None), _icp_row("EAS", 2021, 90.0), _icp_row("XKX", 2021, 55.0)]}}
    df = icp.parse_icp(payload)
    assert set(df.columns) == {"iso_a3", "year", "value"} and len(df) == 5
    out = icp.prepare_household(df).set_index("iso_a2")
    assert out.loc["FR", "pli_household"] == 110.0 and out.loc["FR", "year"] == 2021  # 2022 is null, not "0"
    assert out.loc["XK", "pli_household"] == 55.0
    assert "EAS" not in out["iso_a3"].tolist()  # aggregate without an ISO2 code is dropped


def test_wdi_zip_preamble_metadata_aggregates_and_calibration(tmp_path):
    import zipfile

    api = (
        '"Data Source","World Development Indicators",\n'
        "\n"
        '"Last Updated Date","2026-07-01",\n'
        "\n"
        '"Country Name","Country Code","Indicator Name","Indicator Code","2022","2023","2024","2025",\n'
        '"France","FRA","Price level ratio of PPP conversion factor (GDP) to market exchange rate","PA.NUS.PPPC.RF","1.05","1.08","1.1","",\n'
        '"Germany","DEU","Price level ratio of PPP conversion factor (GDP) to market exchange rate","PA.NUS.PPPC.RF","1.15","1.18","1.2","",\n'
        '"Iceland","ISL","Price level ratio of PPP conversion factor (GDP) to market exchange rate","PA.NUS.PPPC.RF","1.4","1.45","1.5","",\n'
        '"East Asia & Pacific","EAS","Price level ratio of PPP conversion factor (GDP) to market exchange rate","PA.NUS.PPPC.RF","0.7","0.7","0.7","",\n'
        '"Nowhere","XXX","Price level ratio of PPP conversion factor (GDP) to market exchange rate","PA.NUS.PPPC.RF","","","","",\n'
    )
    meta = (
        '"Country Code","Region","IncomeGroup","SpecialNotes","TableName",\n'
        '"FRA","Europe & Central Asia","High income","","France",\n'
        '"DEU","Europe & Central Asia","High income","","Germany",\n'
        '"ISL","Europe & Central Asia","High income","","Iceland",\n'
        '"EAS","","","aggregate","East Asia & Pacific",\n'
        '"XXX","Europe & Central Asia","High income","","Nowhere",\n'
    )
    archive = tmp_path / "API_PA.NUS.PPPC.RF_en_csv_v2.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("API_PA.NUS.PPPC.RF_DS57_en_csv_v2_370312.csv", api)
        z.writestr("Metadata_Country_API_PA.NUS.PPPC.RF_DS57_en_csv_v2_370312.csv", meta)
        z.writestr("Metadata_Indicator_API_PA.NUS.PPPC.RF_DS57_en_csv_v2_370312.csv", '"INDICATOR_CODE","INDICATOR_NAME"\n')
    ratios, regions = icp.read_wdi_zip(archive)
    assert "EAS" not in set(ratios.loc[ratios["Country Code"].isin(regions), "Country Code"])
    household = pd.DataFrame({"iso_a3": ["FRA", "DEU"], "iso_a2": ["FR", "DE"], "pli_household": [110.0, 120.0], "year": [2021, 2021]})
    out = icp.prepare_gdp(ratios, regions, household, this_year=2026).set_index("iso_a2")
    # the WDI series is a ratio with the US = 1; it is rescaled onto the ICP world base through
    # the countries both cover (here 110 / 1.1 = 120 / 1.2 = 100), so Iceland lands on 150
    assert out.loc["IS", "pli_gdp"] == pytest.approx(150.0) and out.loc["IS", "year"] == 2024
    assert out.loc["FR", "pli_gdp"] == pytest.approx(110.0)
    assert not {"EAS", "XXX"} & set(out["iso_a3"])  # aggregate and all-blank rows are dropped, never 0


def test_wdi_calibration_refuses_when_nothing_overlaps():
    ratios = pd.DataFrame({"Country Name": ["Iceland"], "Country Code": ["ISL"], "Indicator Name": ["x"], "Indicator Code": ["PA.NUS.PPPC.RF"], "2024": [1.5]})
    household = pd.DataFrame({"iso_a3": ["FRA"], "iso_a2": ["FR"], "pli_household": [110.0], "year": [2021]})
    with pytest.raises(RuntimeError, match="no country"):
        icp.prepare_gdp(ratios, {"ISL"}, household, this_year=2026)


# ---- HUD fair market rents (rent) ------------------------------------------------------------


def test_hud_prepare_prefers_the_whole_county_row_and_medians_town_rows():
    fmr = pd.DataFrame(
        {
            "fips2010": ["0100199999", "2500100120", "2500100380", "2500100460", "0600799999", "0800199999"],
            "state": ["AL", "MA", "MA", "MA", "CA", "CO"],
            "countyname": ["Autauga County", "Barnstable County", "Barnstable County", "Barnstable County", "Butte County", "Adams County"],
            "metro": [1, 1, 1, 1, 1, 1],
            "fmr_0": [800, 1200, 1300, 1250, 900, 1000],
            "fmr_1": [900, 1300, 1400, 1350, 1000, 1100],
            "fmr_2": [1000, 1500, 1700, 1600, "(NA)", 1450],
            "fmr_3": [1300, 1900, 2100, 2000, 1500, 1800],
            "fmr_4": [1500, 2200, 2400, 2300, 1700, 2100],
        }
    )
    out = hud.prepare(fmr).set_index("GEOID")
    assert out.loc["01001", "fmr_2br"] == 1000.0
    assert out.loc["25001", "fmr_2br"] == 1600.0  # median of the three New England town rows
    assert "06007" not in out.index  # missing rent stays missing, never 0
    assert out.loc["08001", "fmr_2br"] == 1450.0


def test_hud_prepare_pads_integer_fips_and_accepts_the_older_column_names():
    fmr = pd.DataFrame({"fips": [100199999, 401399999], "fmr2": [1000, 1450]})  # leading zero lost by Excel (01001, 04013)
    out = hud.prepare(fmr).set_index("GEOID")
    assert list(out.index) == ["01001", "04013"] and out.loc["04013", "fmr_2br"] == 1450.0


# ---- Session 8: Eurostat census grid, English IoD 2025 ----------------------------------------


def test_eurostat_grd_id_parses_to_cell_centres():
    from pipeline.prep.eurostat_grid import parse_grd_id, to_wgs84

    x, y = parse_grd_id(pd.Series(["CRS3035RES1000mN2684000E4334000", "AT_unallocated"]))
    assert x[0] == 4334500.0 and y[0] == 2684500.0 and pd.isna(x[1])
    lat, lng = to_wgs84(x[:1], y[:1])
    assert 40 < lat[0] < 50 and 5 < lng[0] < 20  # the Alps


def test_eurostat_loader_turns_sentinels_into_missing():
    from pipeline.prep.eurostat_grid import load_frame

    df = pd.DataFrame({
        "GRD_ID": ["CRS3035RES1000mN2684000E4334000", "CRS3035RES1000mN2685000E4334000", "CRS3035RES1000mN2686000E4334000", "FR_unallocated"],
        "T": [100, 10, 50, 7], "Y_1564": [60, 0, 30, 5], "Y_GE65": [20, 8, -8888, 1], "EMP": [30, 0, -9999, 2],
    })
    out = load_frame(df)
    assert len(out) == 3  # unallocated population has no location
    assert out["emp_rate"].round(2).tolist()[0] == 0.5
    assert pd.isna(out["emp_rate"].iloc[1])  # no working-age population -> missing, not 0
    assert pd.isna(out["emp_rate"].iloc[2]) and pd.isna(out["share_ge65"].iloc[2])  # confidential / not available
    assert not (out[["pop", "pop_1564", "emp"]] < 0).any().any()


def test_imd_loader_joins_scores_to_lsoas(tmp_path):
    from pipeline.prep import imd

    header = ",".join(f'"{h}"' for h in imd.COLUMNS.values())
    (tmp_path / "f7.csv").write_text(header + "\nE01000001,25.5,0.2,0.1,0.5,20.0,1600,950\n", encoding="utf-8")
    gpd.GeoDataFrame(
        {"LSOA21CD": ["E01000001", "W01000001"], "LSOA21NM": ["City 001A", "Cardiff 001A"]},
        geometry=[box(0, 51, 0.01, 51.01), box(-3.2, 51.4, -3.19, 51.41)],
        crs=4326,
    ).to_file(tmp_path / "lsoa.geojson", driver="GeoJSON")
    out = imd.load_frames(tmp_path / "f7.csv", tmp_path / "lsoa.geojson").set_index("LSOA21CD")
    assert len(out) == 2 and out.loc["E01000001", "emp_dep_rate"] == 0.1 and out.loc["E01000001", "pop_working"] == 950
    assert out.loc["W01000001", ["emp_dep_rate", "health_dep", "housing_barriers"]].isna().all()  # IoD is England only


def test_imd_loader_names_a_missing_column(tmp_path):
    from pipeline.prep import imd

    (tmp_path / "f7.csv").write_text('"LSOA code (2021)"\nE01000001\n', encoding="utf-8")
    with pytest.raises(KeyError, match="IoD2025 File 7"):
        imd.load_frames(tmp_path / "f7.csv", tmp_path / "nope.geojson")
