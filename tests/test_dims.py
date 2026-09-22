from __future__ import annotations

import h3
import numpy as np
import pandas as pd

from pipeline import sanity
from pipeline.config import RES_TAGS
from pipeline.stages import admin, dims, fetch, grid, hazards, pop


def _run_all(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)


def _cell(lat, lng):
    return h3.latlng_to_cell(lat, lng, 4)


def test_wb_joins_shdi_then_whr(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    a_north = df[df["admin1_name"] == "A-North"]
    assert (a_north["wb_raw"] == np.float32(0.82)).all()
    assert (a_north["wb_res"] == "admin1").all() and (a_north["wb_lbl"] == "shdi").all()
    b_mid = df[df["admin1_name"] == "B-Mid"]  # no SHDI region -> national WHR fallback
    assert (b_mid["wb_raw"] == np.float32(5.1)).all()
    assert (b_mid["wb_res"] == "national").all() and (b_mid["wb_lbl"] == "whr").all()
    assert df["wb_res"].isin(RES_TAGS).all()


def test_dims_never_writes_zero_for_missing(settings):
    _run_all(settings)
    df = pd.read_parquet(settings.stage_path("dims", 4))
    for col in [c for c in df.columns if c.endswith("_raw") or c.endswith("_lean")]:
        base = col.rsplit("_", 1)[0]
        tag = df[f"{base}_res"]
        assert df.loc[tag == "none", col].isna().all(), col
        assert df.loc[tag != "none", col].notna().all(), col
    assert df.loc[df["race_res"] == "none", "race_w"].isna().all()
    assert (df.loc[df["race_res"] == "none", "race_maj"] == "none").all()


def test_life_dims_global_fallbacks(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    xa = df[(df["iso_a2"] == "XA") & (df["lng"] < 11.5)]  # away from the XKB border where tracts could leak in
    xb = df[(df["iso_a2"] == "XB") & (df["lng"] > 12.5)]
    # jobs: OECD TL2 stand-in covers XKA (admin1, oecd domain); XKB is tract-covered by the ACS stand-in
    assert (xa["jobs_res"] == "admin1").all() and (xa["jobs_dom"] == "oecd").all()
    assert set(xa["jobs_raw"].round(2)) <= {6.5, 8.0}
    assert (xb["jobs_res"] == "tract").all() and (xb["jobs_dom"] == "us").all()
    # incmix: ACS entropy in XKB, GSAP share above the poverty line in XKA
    assert (xb["incmix_res"] == "tract").all()
    assert (xa["incmix_res"] == "admin1").all() and (np.isclose(xa["incmix_raw"], 0.95) | np.isclose(xa["incmix_raw"], 0.85)).all()
    # house / health: OECD in XKA, ACS / HRSA in XKB
    assert (xa["house_res"] == "admin1").all() and (xb["house_res"] == "tract").all()
    assert (xa["health_res"] == "admin1").all() and (xb["health_res"] == "county").all()


def test_us_life_dims_on_fixtures(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4).set_index("h3")
    cedar = df.loc[_cell(42.5, 13.0)]
    assert cedar["transit_res"] == "tract" and cedar["transit_raw"] > 0
    assert cedar["school_res"] == "county" and 70 <= cedar["school_raw"] <= 95
    assert cedar["lgbtq_res"] == "tract" and cedar["lgbtq_raw"] > 2
    assert cedar["pol_res"] == "county" and -100 <= cedar["pol_lean"] <= 100
    shares = [cedar[f"race_{k}"] for k in ("w", "b", "h", "a", "o")]
    assert sum(shares) == 100 and cedar["race_maj"] in {"w", "b", "h", "a", "o"} and cedar["race_res"] == "tract"
    assert cedar["health_res"] == "county" and cedar["health_raw"] == 35.0
    alder = df.loc[_cell(43.0, 11.0)]  # XKA: no US-only dimension
    for dim in ("transit", "school", "lgbtq", "pol", "race"):
        assert alder[f"{dim}_res"] == "none", dim
    assert pd.isna(alder["pol_lean"]) and alder["race_maj"] == "none" and pd.isna(alder["race_w"])
    # SLD stand-in stops at lng 12.6: XKB hexes west of it have no transit value, never 0
    west = df[(df["iso_a2"] == "XB") & (df["lng"] < 12.3)]
    assert (west["transit_res"] == "none").all() and west["transit_raw"].isna().all()


def test_dims_is_idempotent(settings, capsys):
    _run_all(settings)
    capsys.readouterr()
    dims.run(settings)
    assert "up to date" in capsys.readouterr().out
