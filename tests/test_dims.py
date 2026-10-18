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
    xa = df[(df["iso_a2"] == "XA") & (df["lng"] < 10.6)]  # west XKA: away from the XKB tracts and the east-XKA grid / LSOA stand-ins
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


def test_cost_and_rent_on_fixtures(settings):
    """cost: BEA metro (county) inside the fixture metro, BEA state (admin1) elsewhere in XKB,
    the WDI fallback for the one XKB region the state stand-in leaves out, ICP national in XKA.
    rent: HUD-like county rents cover every XKB county; nothing outside the US-like country."""
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    xa = df[df["iso_a2"] == "XA"]
    xb = df[df["iso_a2"] == "XB"]
    # rent (US only)
    assert (xb["rent_res"] == "county").all() and xb["rent_raw"].between(700, 1450).all()
    assert (xa["rent_res"] == "none").all() and xa["rent_raw"].isna().all()
    # cost: metro > state > ICP > WDI, first hit wins (SPEC §20.2)
    b_mid = xb[xb["admin1_name"] == "B-Mid"]  # the fixture metro (Cedar Co)
    assert len(b_mid) and (b_mid["cost_res"] == "county").all() and (b_mid["cost_lbl"] == "bea").all()
    assert (b_mid["cost_raw"] == np.float32(108.5)).all() and (b_mid["cost_dom"] == "us").all()
    b_north = xb[xb["admin1_name"] == "B-North"]  # no metro row: state price parity
    assert len(b_north) and (b_north["cost_res"] == "admin1").all() and (b_north["cost_raw"] == np.float32(97.0)).all()
    b_south = xb[xb["admin1_name"] == "B-South"]  # neither metro nor state: WDI GDP price level
    assert len(b_south) and (b_south["cost_res"] == "national").all() and (b_south["cost_lbl"] == "wdi").all()
    assert (b_south["cost_raw"] == np.float32(121.0)).all() and (b_south["cost_dom"] == "global").all()
    assert len(xa) and (xa["cost_res"] == "national").all() and (xa["cost_lbl"] == "icp").all()
    assert (xa["cost_raw"] == np.float32(88.0)).all()


def test_dims_is_idempotent(settings, capsys):
    _run_all(settings)
    capsys.readouterr()
    dims.run(settings)
    assert "up to date" in capsys.readouterr().out


def test_overlay_chunking_does_not_change_results(settings, monkeypatch):
    _run_all(settings)
    full = pd.read_parquet(settings.stage_path("dims", 4))
    monkeypatch.setattr(dims, "OVERLAY_CHUNK", 7)
    settings.force = True
    dims.run(settings)
    chunked = pd.read_parquet(settings.stage_path("dims", 4))
    for col in ("jobs_raw", "race_w", "transit_raw", "house_raw"):
        pd.testing.assert_series_equal(full[col], chunked[col], check_exact=False, rtol=1e-6)


def test_grid_and_imd_joiners_fill_the_fixture_regions(settings):
    from pipeline.stages import urban

    settings.res = [4, 5, 6]
    fetch.run(settings)
    urban.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    dims.run(settings)
    d6 = sanity.load_merged(settings, 6)
    inh = d6[d6["inhabited"]]
    east = inh[inh["iso_a2"] == "XA"]
    north = east[(east["lng"] > 11.1) & (east["lng"] < 11.9) & (east["lat"] > 42.1)]
    south = east[(east["lng"] > 11.1) & (east["lng"] < 11.9) & (east["lat"] < 41.9)]
    assert len(north) and len(south)
    assert (north["jobs_res"] == "grid").all() and (north["jobs_dom"] == "eu").all()
    assert d6.loc[d6["jobs_res"] == "grid", "jobs_raw"].between(0.3, 0.9).all()
    for dim in ("jobs", "health", "house"):  # IoD stand-in over south-east XKA
        assert (south[f"{dim}_res"] == "area").all() and (south[f"{dim}_dom"] == "uk").all(), dim
    assert south["jobs_raw"].between(0.05, 0.25).all()  # the employment deprivation rate, not reflected in _raw


def test_ngo_hex_layers_on_fixtures(settings):
    # after Session 8: travel time to cities (raster), relative wealth scored within each country
    # (point_radius mean, per-country domain), conflict deaths within 25 km (point_radius sum)
    from pipeline.stages import score

    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)
    score.run(settings)
    df = sanity.load_merged(settings, 4)
    inh = df[df["inhabited"]]
    assert (inh["city_res"] == "hex").mean() > 0.95 and inh["city_raw"].min() >= 0
    assert set(inh["wealth_dom"].dropna()) == {"country:XA", "country:XB"}
    for dom in ("country:XA", "country:XB"):  # ranked within each country, so each spans the scale
        s = inh.loc[inh["wealth_dom"] == dom, "wealth_score"].astype(float)
        assert s.min() <= 20 and s.max() >= 80, dom
    assert (inh["conflict_res"] == "hex").all() and (inh["conflict_raw"] == 0).any()  # a real zero: no event nearby
    cedar = df.set_index("h3").loc[_cell(42.5, 13.0)]
    assert cedar["conflict_raw"] > 0
    # walking time to care (raster) and working water points within 5 km (missing where none recorded)
    assert (inh["walkcare_res"] == "hex").mean() > 0.95 and (inh["walkcare_raw"] >= inh["care_raw"]).mean() > 0.9
    assert inh["water_raw"].dropna().between(0, 1).all() and inh["water_raw"].notna().any()
    assert inh["water_raw"].isna().any() and (inh.loc[inh["water_raw"].isna(), "water_res"] == "none").all()


def _own_source_input(settings, dim_id):
    """A raw input file that only `dim_id` reads (so touching it stales that dimension alone)."""
    from pipeline.registry import load_dimensions, load_sources

    sources = load_sources(settings.sources_path)
    all_dims = [d for d in load_dimensions(settings.dimensions_path, sources).values() if d.joiners and d.group != "hazard"]
    mine = set(dims._dim_inputs(settings, next(d for d in all_dims if d.id == dim_id), sources, 4))
    others = set().union(*(dims._dim_inputs(settings, d, sources, 4) for d in all_dims if d.id != dim_id))
    own = sorted(p for p in mine - others if p.exists())
    assert own, f"{dim_id} has no input of its own in the fixture world"
    return own[0]


def _touch(path):
    import os

    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))


def test_dims_recomputes_only_the_dimension_whose_source_changed(settings, capsys):
    _run_all(settings)
    _touch(_own_source_input(settings, "care"))
    capsys.readouterr()
    dims.run(settings)
    out = capsys.readouterr().out
    assert "dimensions changed (care)" in out and "res 4: jobs" not in out
    dims.run(settings)
    assert "up to date" in capsys.readouterr().out


def test_dims_only_never_marks_another_stale_dimension_fresh(settings, capsys):
    _run_all(settings)
    _touch(_own_source_input(settings, "care"))
    dims.run(settings, only=["net"])  # forces net; care is still stale
    capsys.readouterr()
    dims.run(settings)
    assert "dimensions changed (care)" in capsys.readouterr().out


def test_dims_code_change_reruns(settings, capsys, monkeypatch):
    from pipeline import stage_cache

    _run_all(settings)
    real = stage_cache.code_version
    monkeypatch.setattr(stage_cache, "code_version", lambda name: "edited" if name == "pipeline.stages.dims" else real(name))
    capsys.readouterr()
    dims.run(settings)
    assert "up to date" not in capsys.readouterr().out


def test_partial_recompute_keeps_the_record_of_missing_sources(settings):
    import json

    from pipeline import stage_cache

    _run_all(settings)
    out = settings.stage_path("dims", 4)
    meta = stage_cache.read_meta(out)
    meta["skipped_sources"] = {"acs_summary": "not downloaded"}  # as if a real download were missing
    stage_cache.meta_path(out).write_text(json.dumps(meta), encoding="utf-8")
    _touch(_own_source_input(settings, "care"))
    dims.run(settings)  # recomputes care only; acs_summary was not tried
    assert stage_cache.read_meta(out)["skipped_sources"] == {"acs_summary": "not downloaded"}
