from __future__ import annotations

import json

import pytest

from pipeline import stage_cache
from pipeline.stages import admin, dims, export, fetch, grid, hazards, pop, score, tiles, validate


def _build(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)
    score.run(settings)
    export.run(settings)
    tiles.run(settings, backend="python", workers=0)


def _manifest(settings) -> dict:
    return json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))


def _write(settings, m: dict) -> None:
    (settings.out_dir / "manifest.json").write_text(json.dumps(m), encoding="utf-8")


def _errors(findings):
    return [f.message for f in findings if f.level == "error"]


def test_a_clean_fixture_build_passes(settings):
    _build(settings)
    findings = validate.run(settings)
    assert _errors(findings) == []
    assert json.loads((settings.out_dir / "validate.json").read_text(encoding="utf-8"))["findings"] == [vars(f) for f in findings]


def test_release_mode_refuses_fixture_and_bbox_builds(settings):
    _build(settings)
    msgs = _errors(validate.check(settings, release=True))
    assert any("fixture build" in m for m in msgs)


def test_a_tampered_archive_is_caught(settings):
    _build(settings)
    path = settings.out_dir / "hexes.pmtiles"
    data = bytearray(path.read_bytes())
    data[-1] ^= 0xFF  # same size, different bytes
    path.write_bytes(bytes(data))
    assert any("does not match the sha256" in m for m in _errors(validate.check(settings)))


def test_an_archive_missing_from_the_manifest_is_caught(settings):
    _build(settings)
    m = _manifest(settings)
    m["tiles"] = {}
    _write(settings, m)
    assert any("is not built" in m for m in _errors(validate.check(settings)))


def test_tiles_code_change_makes_the_archive_stale(settings, monkeypatch):
    _build(settings)
    real = stage_cache.code_version
    monkeypatch.setattr(stage_cache, "code_version", lambda name: "edited" if name == "pipeline.stages.tiles" else real(name))
    assert any("older than its parquet, plan or code" in m for m in _errors(validate.check(settings)))


def test_an_empty_dimension_is_an_error_when_its_sources_loaded(settings):
    _build(settings)
    m = _manifest(settings)
    for d in m["dimensions"]:
        if d["id"] == "jobs":
            n = sum(d["coverage"]["4"].values())
            d["coverage"]["4"] = {"none": n}
    _write(settings, m)
    assert any("jobs reaches no inhabited hex" in m for m in _errors(validate.check(settings)))


def test_an_empty_dimension_whose_sources_are_not_downloaded_is_a_warning(settings, monkeypatch):
    _build(settings)
    m = _manifest(settings)
    for d in m["dimensions"]:
        if d["id"] == "pol":
            d["coverage"]["4"] = {"none": sum(d["coverage"]["4"].values())}
    _write(settings, m)
    from pipeline.registry import load_dimensions, load_sources

    pol_sources = {s.source for s in load_dimensions(settings.dimensions_path, load_sources(settings.sources_path))["pol"].joiners}
    monkeypatch.setattr(validate, "_skipped", lambda settings, res: pol_sources)
    findings = validate.check(settings)
    assert not any("pol" in m for m in _errors(findings))
    assert any(f.level == "warn" and "pol has no data" in f.message for f in findings)


def test_a_missing_hazard_is_an_error(settings):
    _build(settings)
    m = _manifest(settings)
    m["known_gaps"]["4"]["heat"]["inhabited_hexes_without_data"] = m["coverage_summary"]["4"]["hexes_inhabited"]
    _write(settings, m)
    assert any("heat has no value" in m for m in _errors(validate.check(settings)))


def test_regression_against_the_baseline(settings):
    _build(settings)
    base = _manifest(settings)
    assert _errors(validate.check(settings, baseline=base)) == []  # the same build is no regression
    base["built_at"] = "2026-01-01T00:00:00+00:00"
    base["coverage_summary"]["4"]["hexes_inhabited"] *= 2
    msgs = _errors(validate.check(settings, baseline=base))
    assert any("inhabited hexes fell" in m for m in msgs)
    assert _errors(validate.check(settings, baseline=base, max_drop=0.6)) == []
    base["dimensions"].append({"id": "gone", "coverage": {}})
    assert any("gone was in" in m for m in _errors(validate.check(settings, baseline=base, max_drop=0.6)))


def test_run_raises_with_a_readable_sentence(settings):
    _build(settings)
    m = _manifest(settings)
    m["tiles"] = {}
    _write(settings, m)
    with pytest.raises(ValueError, match=r"validate found 1 problem\(s\), the first: hexes.pmtiles is not built"):
        validate.run(settings)
