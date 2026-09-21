from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline.config import Settings, find_root
from pipeline.fixtures import make_fixtures

ROOT = find_root(Path(__file__))


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return make_fixtures.ensure(ROOT / "pipeline" / "fixtures" / "data")


@pytest.fixture()
def settings(fixture_dir: Path, tmp_path: Path, monkeypatch) -> Settings:
    """Fixture-mode settings whose run directory is a fresh temp dir."""
    s = Settings(root=ROOT, fixtures=True, res=[4], iso_overrides=dict(make_fixtures.ISO_OVERRIDES))
    run_dir = tmp_path / "_run"
    monkeypatch.setattr(Settings, "data_dir", property(lambda self: run_dir))
    s.ensure_dirs()
    yield s
    shutil.rmtree(run_dir, ignore_errors=True)
