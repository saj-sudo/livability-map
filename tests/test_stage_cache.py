from __future__ import annotations

from pipeline import stage_cache


def _pkg(tmp_path, files: dict[str, str]):
    root = tmp_path / "pkg"
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
    return root


def test_closure_follows_relative_and_absolute_imports(tmp_path):
    root = _pkg(tmp_path, {
        "__init__.py": "",
        "stages/__init__.py": "",
        "stages/a.py": "from .. import helper\nfrom ..deep.mod import f\n",
        "helper.py": "import pkg.other\n",
        "other.py": "X = 1\n",
        "deep/__init__.py": "",
        "deep/mod.py": "def f():\n    return 2\n",
        "unused.py": "Y = 3\n",
    })
    closure = stage_cache.module_closure("pkg.stages.a", root)
    assert set(closure) == {"pkg", "pkg.stages.a", "pkg.helper", "pkg.other", "pkg.deep.mod", "pkg.deep"}


def test_digest_ignores_comments_and_docstrings_but_not_code(tmp_path):
    base = {"__init__.py": "", "m.py": '"""doc"""\nX = 1  # note\n'}
    d0 = stage_cache.module_closure("pkg.m", _pkg(tmp_path / "a", base))["pkg.m"]
    d1 = stage_cache.module_closure("pkg.m", _pkg(tmp_path / "b", {**base, "m.py": '"""another doc"""\n# a comment\nX = 1\n'}))["pkg.m"]
    d2 = stage_cache.module_closure("pkg.m", _pkg(tmp_path / "c", {**base, "m.py": "X = 2\n"}))["pkg.m"]
    assert d0 == d1 and d0 != d2


def test_real_stage_closures_reach_what_they_run():
    dims = stage_cache.module_closure("pipeline.stages.dims")
    assert "pipeline.joiners.point_radius" in dims  # imported by the joiners package
    assert "pipeline.prep.acs" in dims  # registered lazily as "pipeline.prep.acs:load"
    assert "pipeline.tiler" in stage_cache.module_closure("pipeline.stages.tiles")
    assert "pipeline.scoring" in stage_cache.module_closure("pipeline.stages.score")
    assert not any(m.startswith("pipeline.fixtures") or m in stage_cache.PLUMBING for m in dims)


def test_fingerprint_moves_with_stage_code(tmp_path, monkeypatch):
    params = {"stage": "pop", "res": 4}
    before = stage_cache.fingerprint([], params)
    real = stage_cache.code_version
    monkeypatch.setattr(stage_cache, "code_version", lambda name: "edited" if name == "pipeline.stages.pop" else real(name))
    assert stage_cache.fingerprint([], params) != before
    assert stage_cache.fingerprint([], {"stage": "grid", "res": 4}) == stage_cache.fingerprint([], {"stage": "grid", "res": 4})


def test_a_replaced_output_is_not_fresh(tmp_path):
    out = tmp_path / "x.parquet"
    out.write_bytes(b"abc")
    stage_cache.record(out, [], {"stage": "pop"})
    assert stage_cache.is_fresh(out, [], {"stage": "pop"})
    out.write_bytes(b"abcdef")  # rewritten by something other than the stage
    assert not stage_cache.is_fresh(out, [], {"stage": "pop"})
