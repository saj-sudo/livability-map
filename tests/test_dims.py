from __future__ import annotations

import h3
import numpy as np
import pandas as pd
import pytest

from pipeline import prep, sanity
from pipeline.config import RES_TAGS
from pipeline.registry import load_dimensions, load_sources
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


def test_nri_and_places_tract_dims_on_fixtures(settings):
    _run_all(settings)
    df = sanity.load_merged(settings, 4).set_index("h3")
    cedar = df.loc[_cell(42.5, 13.0)]
    assert cedar["nri_res"] == "tract" and cedar["nri_raw"] > 0 and cedar["nri_lbl"] == "nri"
    assert cedar["phealth_res"] == "tract" and 12 <= cedar["phealth_raw"] <= 22
    alder = df.loc[_cell(43.0, 11.0)]  # XKA: US-only dimensions are missing
    assert alder["nri_res"] == "none" and pd.isna(alder["nri_raw"])
    # PLACES stand-in is blank on XKB's northern edge: missing there, never 0
    north = df[(df["iso_a2"] == "XB") & (df["lat"] > 43.8)]
    assert len(north) and north["phealth_raw"].isna().all() and (north["phealth_res"] == "none").all()


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


def test_overlay_prefilter_matches_the_whole_layer(settings, monkeypatch):
    _run_all(settings)
    monkeypatch.setattr(dims, "OVERLAY_CHUNK", 7)
    settings.force = True
    dims.run(settings)
    narrowed = pd.read_parquet(settings.stage_path("dims", 4))
    monkeypatch.setattr(dims, "_layer_near", lambda layer, chunk, res: layer)
    dims.run(settings)
    whole = pd.read_parquet(settings.stage_path("dims", 4))
    pd.testing.assert_frame_equal(narrowed, whole, check_exact=False, rtol=1e-6)


def test_check_nonnull_stops_on_an_empty_or_mostly_empty_layer():
    ok = pd.DataFrame({"a": [1.0, 2.0, None, 4.0], "b": [1, 2, 3, 4]})
    dims.check_nonnull("src", ok, {"a", "b", "not_a_column"})  # 75% filled; a missing column is the joiner's business
    sparse = pd.DataFrame({"a": [1.0] + [None] * 19})
    with pytest.raises(RuntimeError, match=r"src\.a is filled in 5\.0% .*min_nonnull"):
        dims.check_nonnull("src", sparse, {"a"})
    dims.check_nonnull("src", sparse, {"a"}, minimum=0.05)  # the source's own override
    dims.check_nonnull("src", sparse, {"a"}, minimum=0)  # switched off
    with pytest.raises(RuntimeError, match="no rows"):
        dims.check_nonnull("src", ok.iloc[:0], {"a"})


def test_a_mostly_empty_source_stops_dims_with_a_plain_message(settings, monkeypatch):
    real = prep.load_layer

    def blank(settings, source_id, sources):
        df = real(settings, source_id, sources)
        if source_id == "wb_gsap":
            df = df.copy()
            df["nonpoor_share"] = np.nan
        return df

    monkeypatch.setattr(dims.prep, "load_layer", blank)
    with pytest.raises(RuntimeError, match=r"wb_gsap\.nonpoor_share is filled in 0\.0%"):
        _run_all(settings)


def _store(settings, monkeypatch):
    """A LayerStore over the dimensions that share one source, with a fake loader that counts."""
    sources = load_sources(settings.sources_path)
    todo = [d for d in load_dimensions(settings.dimensions_path, sources).values() if d.joiners and d.group != "hazard"]
    by_source: dict[str, list] = {}
    for d in todo:
        for src in {s.source for s in d.joiners if s.joiner != "raster_mean"}:
            by_source.setdefault(src, []).append(d)
    shared = next(s for s, ds in by_source.items() if len(ds) >= 2)
    loads: list[str] = []

    def fake(settings, source_id, sources):
        loads.append(source_id)
        return pd.DataFrame({f: [1.0, 2.0] for f in store.fields.get(source_id, {"x"})} or {"x": [1.0]})

    monkeypatch.setattr(dims.prep, "load_layer", fake)
    store = dims.LayerStore(settings, by_source[shared], sources, set(), {})
    return store, shared, by_source[shared], loads


def test_layers_load_when_asked_and_are_freed_after_their_last_dimension(settings, monkeypatch):
    store, shared, users, loads = _store(settings, monkeypatch)
    assert loads == [] and not store.layers  # nothing is read up front
    assert store.get(shared) is not None and store.get(shared) is not None
    assert loads == [shared]  # loaded once however often it is asked for
    for d in users[:-1]:
        store.done(d)
        assert shared in store.layers  # a later dimension still needs it
    store.done(users[-1])
    assert shared not in store.layers  # freed with the last user
    assert shared in store.tried


def test_a_missing_download_is_skipped_once_and_reads_as_none(settings, monkeypatch, capsys):
    store, shared, _, _ = _store(settings, monkeypatch)

    def gone(settings, source_id, sources):
        raise FileNotFoundError("download it first")

    monkeypatch.setattr(dims.prep, "load_layer", gone)
    assert store.get(shared) is None and store.get(shared) is None
    assert capsys.readouterr().out.count("skipping joiner source") == 1
    assert "download it first" in store.skipped[shared]


# ---- crash resume (checkpoint shards) -----------------------------------------------------------


class _Crash(RuntimeError):
    pass


def _spy_join(monkeypatch, crash_on: int | None = None) -> list[str]:
    """Record the id of every dimension joined; the ``crash_on``-th call (1-based) raises."""
    real = dims.join_dimension
    calls: list[str] = []

    def spy(dim, *args, **kwargs):
        calls.append(dim.id)
        if crash_on is not None and len(calls) == crash_on:
            raise _Crash(f"died while joining {dim.id}")
        return real(dim, *args, **kwargs)

    monkeypatch.setattr(dims, "join_dimension", spy)
    return calls


def _prepare(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)


def test_a_crashed_dims_run_resumes_from_its_checkpoints(settings, monkeypatch, capsys):
    _prepare(settings)
    parts = settings.interim_dir / "dims_r4.parts"
    done = _spy_join(monkeypatch)
    settings.force = True
    dims.run(settings)  # a clean run to learn the dimension order and the expected output
    order, clean = list(done), pd.read_parquet(settings.stage_path("dims", 4))
    assert len(order) > 6 and not parts.exists()  # the checkpoints are gone after a successful run
    settings.stage_path("dims", 4).unlink()
    stage_cache_meta = settings.stage_path("dims", 4).with_suffix(".parquet.meta.json")
    stage_cache_meta.unlink()

    settings.force = False
    _spy_join(monkeypatch, crash_on=5)
    with pytest.raises(_Crash):
        dims.run(settings)
    assert sorted(p.stem for p in parts.glob("*.parquet")) == sorted(order[:4])  # four finished, the fifth died
    assert not settings.stage_path("dims", 4).exists()  # no torn or partial final file

    capsys.readouterr()
    calls = _spy_join(monkeypatch)
    dims.run(settings)
    assert calls == order[4:]  # only the rest was computed
    assert capsys.readouterr().out.count("resumed from checkpoint") == 4
    assert not parts.exists()
    pd.testing.assert_frame_equal(pd.read_parquet(settings.stage_path("dims", 4)), clean, check_exact=True)


def test_a_checkpoint_whose_dimension_changed_is_recomputed(settings, monkeypatch):
    _prepare(settings)
    calls = _spy_join(monkeypatch)
    settings.force = True
    dims.run(settings)
    order = list(calls)
    settings.stage_path("dims", 4).unlink()
    settings.stage_path("dims", 4).with_suffix(".parquet.meta.json").unlink()
    settings.force = False
    _spy_join(monkeypatch, crash_on=4)
    with pytest.raises(_Crash):
        dims.run(settings)
    first = order[0]
    real_spec = dims._dim_spec
    monkeypatch.setattr(dims, "_dim_spec", lambda dim, sources, countries=None: "edited" if dim.id == first else real_spec(dim, sources, countries))
    calls = _spy_join(monkeypatch)
    dims.run(settings)
    assert calls == [first, *order[3:]]  # the edited dimension is redone, the other two checkpoints are kept


def test_force_ignores_checkpoints(settings, monkeypatch):
    _prepare(settings)
    calls = _spy_join(monkeypatch)
    settings.force = True
    dims.run(settings)
    total = len(calls)
    settings.stage_path("dims", 4).unlink()
    settings.stage_path("dims", 4).with_suffix(".parquet.meta.json").unlink()
    _spy_join(monkeypatch, crash_on=3)
    with pytest.raises(_Crash):
        dims.run(settings)
    assert (settings.interim_dir / "dims_r4.parts").exists()
    calls = _spy_join(monkeypatch)
    dims.run(settings)  # still forced
    assert len(calls) == total and not (settings.interim_dir / "dims_r4.parts").exists()


def test_only_does_not_touch_another_runs_checkpoints(settings, monkeypatch):
    _prepare(settings)
    dims.run(settings)
    parts = settings.interim_dir / "dims_r4.parts"
    parts.mkdir()
    (parts / "keep.parquet").write_bytes(b"x")  # a leftover from some crashed run
    dims.run(settings, only=["care"])
    assert (parts / "keep.parquet").exists() and not (parts / "care.parquet").exists()


def test_leftover_checkpoints_are_dropped_when_the_final_file_is_already_fresh(settings, monkeypatch):
    _prepare(settings)
    dims.run(settings)
    parts = settings.interim_dir / "dims_r4.parts"
    parts.mkdir()
    (parts / "care.parquet").write_bytes(b"junk")  # what a crashed forced run would have left behind
    calls = _spy_join(monkeypatch)
    dims.run(settings)
    assert calls == [] and not parts.exists()


def test_us_layers_never_spill_into_the_neighbouring_country(settings):
    """§13.45: the fixture's US-like tracts reach a few XKA border hexes; those hexes stay missing
    (and unranked against XKB) instead of taking a US value."""
    _run_all(settings)
    df = sanity.load_merged(settings, 4)
    xa = df[df["iso_a2"] == "XA"]
    for dim in ("lgbtq", "incmix", "nri", "phealth", "school"):
        assert not (xa[f"{dim}_dom"] == "us").any(), dim
    assert not (xa["race_dom"] == "us").any() and xa.loc[xa["race_res"] == "tract"].empty


def test_a_single_country_joiner_leaves_other_countries_to_the_next_joiner():
    """A polygon covering two countries fills only its own country's hexes; the hex across the
    border falls through to the next joiner (here a global one)."""
    import geopandas as gpd
    import shapely

    from pipeline.registry import Dimension, JoinSpec

    cells = [_cell(42.0, 12.0), _cell(42.0, 13.0)]
    lat, lng = zip(*(h3.cell_to_latlng(c) for c in cells), strict=True)
    hexes = pd.DataFrame({"h3": cells, "lat": lat, "lng": lng, "iso_a2": ["XA", "XB"], "inhabited": [True, True]})
    tracts = gpd.GeoDataFrame({"v": [7.0]}, geometry=[shapely.box(10, 40, 14, 44)], crs=4326)
    world = gpd.GeoDataFrame({"v": [1.0]}, geometry=[shapely.box(10, 40, 14, 44)], crs=4326)
    dim = Dimension(
        id="t", name="t", group="life", kind="score", higher_is="better", coverage=[],
        joiners=[
            JoinSpec(source="tracts", joiner="area_weighted_overlay", res="tract", field="v", domain="us"),
            JoinSpec(source="world", joiner="polygon_centroid", res="admin1", field="v", domain="global"),
        ],
    )
    got = dims.join_dimension(dim, hexes, 4, {"tracts": tracts, "world": world}, domain_countries={"us": ("XB",)})
    assert list(got["t_raw"]) == [1.0, 7.0]
    assert list(got["t_dom"]) == ["global", "us"] and list(got["t_res"]) == ["admin1", "tract"]
    # without the map the old first-hit-wins behaviour returns: both hexes take the US value
    loose = dims.join_dimension(dim, hexes, 4, {"tracts": tracts, "world": world})
    assert list(loose["t_raw"]) == [7.0, 7.0]
