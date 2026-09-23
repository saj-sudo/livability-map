"""Country small-area / grid loaders added after Session 8 (SPEC §13.34, §15): each parses the real
file layout recorded in §15, keeps missing as missing (never 0) and outputs the columns
dimensions.yaml names."""

from __future__ import annotations

import io
import zipfile

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

# ---- Germany: Zensus 2022 100 m grid (rent) -------------------------------------------------------


def test_zensus_rent_grid_parses_decimal_commas_and_cell_centres():
    from pipeline.prep.de_zensus import load_csv

    text = (
        "GITTER_ID_100m;x_mp_100m;y_mp_100m;durchschnMieteQM;AnzahlWohnungen;werterlaeuternde_Zeichen\n"
        "CRS3035RES100mN2691700E4341100;4341150;2691750;6,26;12;\n"
        "CRS3035RES100mN3270100E4553200;4553250;3270150;13,5;40;KLAMMERN\n"
    )
    out = load_csv(io.StringIO(text))
    assert out["rent_eur_m2"].tolist() == [6.26, 13.5]
    assert out["dwellings"].tolist() == [12, 40]
    assert out["lat"].between(47, 55).all() and out["lng"].between(5, 16).all()  # inside Germany


# ---- Netherlands: CBS 100 m / 500 m squares -------------------------------------------------------


def _cbs_gpkg(tmp_path, layer, **cols):
    gdf = gpd.GeoDataFrame(cols, geometry=[box(155000, 463000, 155100, 463100), box(121000, 487000, 121100, 487100)], crs=28992)
    path = tmp_path / f"{layer}.gpkg"
    gdf.to_file(path, layer=layer, driver="GPKG")
    return path


def test_cbs_squares_turn_sentinels_into_missing(tmp_path):
    from pipeline.prep.nl_cbs import load_squares

    path = _cbs_gpkg(tmp_path, "cbs_vk100_2023", gemiddelde_woz_waarde_woning=[357.0, -99997.0], aantal_woningen=[40, -99997])
    out = load_squares(path, "cbs_vk100_2023", {"gemiddelde_woz_waarde_woning": "woz_keur", "aantal_woningen": "homes"})
    assert out["woz_keur"].iloc[0] == 357.0 and pd.isna(out["woz_keur"].iloc[1])  # -99997 = 0-4 / secret
    assert pd.isna(out["homes"].iloc[1])
    assert out["lat"].between(50.7, 53.6).all() and out["lng"].between(3.3, 7.3).all()  # inside the Netherlands


# ---- France: INSEE IRIS + IGN contours ------------------------------------------------------------


def _zip(path, member, text):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, text)
    return path


def test_iris_tables_join_to_contours_with_ns_as_missing(tmp_path):
    from pipeline.prep.fr_iris import load_frames

    act = _zip(tmp_path / "act.zip", "base-ic-activite-residents-2021.CSV", "IRIS;COM;P21_POP1564;P21_ACTOCC1564\n751010101;75101;1000.5;700.25\n130010102;13001;0;0\n")
    filo = _zip(tmp_path / "filo.zip", "BASE_TD_FILO_IRIS_2021_DISP.csv", "IRIS;DISP_TP6021;DISP_MED21\n751010101;12,5;30000\n130010102;ns;nd\n")
    contours = gpd.GeoDataFrame({"CODE_IRIS": ["751010101", "130010102", "976010000"]}, geometry=[box(2.3, 48.85, 2.31, 48.86), box(5.37, 43.29, 5.38, 43.3), box(45.1, -12.8, 45.2, -12.7)], crs=4326)
    out = load_frames(act, "base-ic-activite-residents-2021.CSV", filo, "BASE_TD_FILO_IRIS_2021_DISP.csv", contours).set_index("CODE_IRIS")
    assert out.loc["751010101", "emp_rate"] == pytest.approx(700.25 / 1000.5)
    assert out.loc["751010101", "poverty_rate"] == 12.5
    assert pd.isna(out.loc["130010102", "emp_rate"])  # no working-age population: missing, not 0
    assert pd.isna(out.loc["130010102", "poverty_rate"])  # "ns" (not significant)
    assert pd.isna(out.loc["976010000", "pop_1564"])  # Mayotte: contour without census row
    assert out.crs.to_epsg() == 4326


# ---- Canada: StatCan 2021 Census Profile, dissemination areas ------------------------------------

CA_HEADER = "CENSUS_YEAR,DGUID,ALT_GEO_CODE,GEO_LEVEL,GEO_NAME,TNR_SF,TNR_LF,DATA_QUALITY_FLAG,CHARACTERISTIC_ID,CHARACTERISTIC_NAME,CHARACTERISTIC_NOTE,C1_COUNT_TOTAL,SYMBOL,C2_COUNT_MEN+,SYMBOL,C3_COUNT_WOMEN+,SYMBOL,C10_RATE_TOTAL,SYMBOL,C11_RATE_MEN+,SYMBOL,C12_RATE_WOMEN+,SYMBOL\r\n"


def _ca_row(dguid, level, cid, value, symbol=""):
    return f'2021,"{dguid}","{dguid[-8:]}","{level}","Qu\xe9bec",1,2,"00000",{cid},"name",,{value},{symbol},,,,,,,,,,\r\n'


def test_statcan_profile_pivots_das_and_keeps_suppressed_as_missing(tmp_path):
    from pipeline.prep.ca_statcan import load_profile

    rows = [_ca_row("2021A000011124", "Country", 1, 36991981)]
    a, b = "2021S051210010732", "2021S051224690104"
    for cid, v in ((1, 500), (345, 9.5), (1465, 200), (1467, 30), (2223, 400), (2229, 60.1)):
        rows.append(_ca_row(a, "Dissemination area", cid, v))
    rows += [_ca_row(b, "Dissemination area", 1, 20), _ca_row(b, "Dissemination area", 2229, "", "x"), _ca_row(b, "Dissemination area", 345, "", "..")]
    path = tmp_path / "profile.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("98-401-X2021006_English_CSV_data_Quebec.csv", (CA_HEADER + "".join(rows)).encode("cp1252"))
    out = load_profile(path, chunksize=3).set_index("DGUID")
    assert list(out.index) == [a, b]  # only dissemination areas
    assert out.loc[a, "emp_rate"] == 60.1 and out.loc[a, "low_income_rate"] == 9.5
    assert out.loc[a, "shelter_burden"] == pytest.approx(30 / 200) and out.loc[a, "households"] == 200
    assert pd.isna(out.loc[b, "emp_rate"]) and pd.isna(out.loc[b, "low_income_rate"])  # "x" / ".." -> missing, never 0
    assert pd.isna(out.loc[b, "shelter_burden"])


# ---- Australia: ABS 2021 GCP DataPack, SA2 ---------------------------------------------------------


def test_abs_datapack_treats_zero_medians_as_missing(tmp_path):
    from pipeline.prep.au_abs import load_datapack

    base = "2021 Census GCP Statistical Area 2 for AUS/2021Census_{}_AUST_SA2.csv"
    path = tmp_path / "gcp.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(base.format("G01"), "SA2_CODE_2021,Tot_P_M,Tot_P_F,Tot_P_P\n101021007,1000,1100,2100\n101021008,0,0,0\n197979799,5,5,10\n")
        z.writestr(base.format("G02"), "SA2_CODE_2021,Median_rent_weekly,Median_tot_hhd_inc_weekly\n101021007,400,2000\n101021008,0,0\n197979799,0,0\n")
        z.writestr(base.format("G43"), "SA2_CODE_2021,P_15_yrs_over_P,Percnt_Employment_to_populn_P\n101021007,1700,58.5\n101021008,0,0\n197979799,8,0\n")
    out = load_datapack(path).set_index("SA2_CODE_2021")
    assert "197979799" not in out.index  # migratory / offshore pseudo-SA2
    assert out.loc["101021007", "emp_rate"] == pytest.approx(0.585)
    assert out.loc["101021007", "rent_share_income"] == pytest.approx(0.2) and out.loc["101021007", "median_rent_weekly"] == 400
    assert out.loc["101021008", ["emp_rate", "rent_share_income", "median_rent_weekly"]].isna().all()  # 0 = not available
