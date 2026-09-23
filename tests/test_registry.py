from __future__ import annotations

import pytest

from pipeline.config import RES_TAGS, find_root
from pipeline.registry import load_dimensions, load_sources

ROOT = find_root()


def test_real_sources_load_and_have_required_fields():
    sources = load_sources(ROOT / "pipeline" / "sources.yaml")
    assert {"natural_earth_land", "ghsl_pop", "geoboundaries_adm0", "geoboundaries_adm1", "cckp_hd35"} <= set(sources)
    for s in sources.values():
        assert s.files, f"{s.id} lists no files"
        assert s.attribution or s.access == "fixture", f"{s.id} has no attribution"
        assert s.extra.get("verified") in ("confirmed", "search", "none"), s.id


def test_dimensions_reference_known_sources_and_res_tags():
    sources = load_sources(ROOT / "pipeline" / "sources.yaml")
    dims = load_dimensions(ROOT / "pipeline" / "dimensions.yaml", sources)
    assert {"heat", "rflood", "cflood", "wstress", "wb", "jobs", "pol", "race"} <= set(dims)
    for d in dims.values():
        for j in d.joiners:
            assert j.res in RES_TAGS
            assert j.source in sources
    assert dims["pol"].kind == "signed"
    assert dims["race"].kind == "composition"
    assert dims["heat"].higher_is == "worse"


def test_fixture_sources_share_ids_with_real_sources():
    real = load_sources(ROOT / "pipeline" / "sources.yaml")
    fix = load_sources(ROOT / "pipeline" / "fixtures" / "sources.yaml")
    shared = {"natural_earth_land", "ghsl_pop", "geoboundaries_adm0", "geoboundaries_adm1", "cckp_hd35", "gdl_shdi", "whr_ladder"}
    assert shared <= set(real) and shared <= set(fix)


def test_unverified_detection():
    fix = load_sources(ROOT / "pipeline" / "fixtures" / "sources.yaml")
    assert fix["unverified_example"].unverified
    assert not fix["natural_earth_land"].unverified


def test_composition_joiners_carry_component_fields():
    dims = load_dimensions(ROOT / "pipeline" / "dimensions.yaml", load_sources(ROOT / "pipeline" / "sources.yaml"))
    assert set(dims["race"].joiners[0].fields) == {"w", "b", "h", "a", "o"}
    assert dims["wb"].scale == "minmax" and dims["wb"].joiners[0].label == "shdi"
    assert dims["jobs"].scale == "percentile"
    assert dims["wb"].to_manifest()["joiners"][1]["label"] == "whr"


def test_dimensions_yaml_rejects_composition_without_fields(tmp_path):
    import pytest

    p = tmp_path / "d.yaml"
    p.write_text("- id: x\n  kind: composition\n  joiners:\n    - {source: s, joiner: polygon_centroid, res: tract, field: f}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fields"):
        load_dimensions(p)


def test_every_real_source_referenced_by_a_dimension_has_geometry_or_is_spatial():
    sources = load_sources(ROOT / "pipeline" / "sources.yaml")
    dims = load_dimensions(ROOT / "pipeline" / "dimensions.yaml", sources)
    for d in dims.values():
        for j in d.joiners:
            s = sources[j.source]
            if j.joiner in ("polygon_centroid", "area_weighted_overlay"):
                assert s.crs or s.extra.get("geometry") in sources, f"{j.source} needs polygons"


def test_every_dimension_and_joiner_states_its_unit():
    """SPEC §6.3: the manifest carries how to print a raw value (unit text, multiply, decimals)
    so the inspector can format a new dimension without code."""
    sources = load_sources(ROOT / "pipeline" / "sources.yaml")
    dims = load_dimensions(ROOT / "pipeline" / "dimensions.yaml", sources)
    for d in dims.values():
        if not d.joiners:
            assert d.unit, f"{d.id}: hazards need a dimension-level unit"
        for j in d.joiners:
            assert j.unit, f"{d.id}/{j.source}: joiner without a unit"
            assert 0 <= j.decimals <= 4 and j.multiply > 0
    assert dims["rflood"].multiply == 100 and dims["rflood"].decimals == 1
    jobs = {j.res: j for j in dims["jobs"].joiners}
    assert jobs["tract"].multiply == 100 and "OECD" in jobs["admin1"].unit
    m = dims["care"].to_manifest()
    assert m["joiners"][0]["unit"].startswith("min") and m["joiners"][0]["decimals"] == 0
    assert dims["heat"].to_manifest()["unit"].startswith("days")


def test_unit_fields_are_validated(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("- id: x\n  kind: score\n  unit: things\n  decimals: 9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="decimals"):
        load_dimensions(p)
    p.write_text("- id: x\n  kind: score\n  unit: things\n  joiners:\n    - {source: s, joiner: iso_lookup, res: national, field: f, multiply: 0}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="multiply"):
        load_dimensions(p)
    # a joiner inherits the dimension's unit when it states none
    p.write_text("- id: x\n  kind: score\n  unit: things\n  decimals: 2\n  joiners:\n    - {source: s, joiner: iso_lookup, res: national, field: f}\n", encoding="utf-8")
    d = load_dimensions(p)["x"]
    assert d.joiners[0].unit == "things" and d.joiners[0].decimals == 2


def test_grid_tag_allowed_only_for_hex_joiners(tmp_path):
    import yaml

    root = find_root()
    sources = load_sources(root / "pipeline" / "sources.yaml")
    ok = {"id": "g", "name": "g", "group": "life", "kind": "score", "sources": ["eurostat_census_grid_2021"], "joiners": [{"source": "eurostat_census_grid_2021", "joiner": "point_mean", "res": "grid", "field": "emp_rate", "domain": "eu", "label": "x"}]}
    bad = {**ok, "joiners": [{"source": "acs_summary", "joiner": "area_weighted_overlay", "res": "grid", "field": "f", "domain": "us", "label": "x"}]}
    p = tmp_path / "dims.yaml"
    p.write_text(yaml.safe_dump([ok]), encoding="utf-8")
    assert "g" in load_dimensions(p, sources)
    p.write_text(yaml.safe_dump([bad]), encoding="utf-8")
    with pytest.raises(ValueError, match="grid"):
        load_dimensions(p, sources)
    assert "grid" in RES_TAGS
