"""Resolution plan (SPEC §9.1, §13.32): loading, validation and the questions stages ask it."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipeline import resplan
from pipeline.config import Settings


def _write(tmp_path: Path, entries) -> Path:
    p = tmp_path / "plan.yaml"
    p.write_text(yaml.safe_dump({"resolutions": entries}), encoding="utf-8")
    return p


GOOD = [
    {"res": 4, "fill": "land", "zooms": [2, 4], "archive": "hexes", "slim_below_zoom": 3},
    {"res": 5, "fill": "land", "zooms": [5, 7], "archive": "hexes"},
    {"res": 6, "fill": "children", "parent": 5, "where": {"countries": ["XA"], "urban": "cluster"}, "zooms": [8, 9], "archive": "hexes_fine"},
    {"res": 7, "fill": "children", "parent": 6, "where": {"urban": "centre"}, "zooms": [10, 13], "archive": "hexes_fine"},
]


def test_plan_loads_and_answers_questions(tmp_path):
    plan = resplan.load_plan(_write(tmp_path, GOOD))
    assert plan.resolutions() == [4, 5, 6, 7]
    assert plan.entry(6).parent == 5 and plan.entry(6).where["countries"] == ["XA"]
    assert plan.reference_res(7) == 5 and plan.reference_res(6) == 5 and plan.reference_res(5) is None
    assert plan.next_finer(5).res == 6 and plan.next_finer(7) is None
    assert plan.archives() == {"hexes": [4, 5], "hexes_fine": [6, 7]}
    assert plan.to_manifest()[2]["where"] == {"countries": ["XA"], "urban": "cluster"}
    assert plan.entry(4).complete and not plan.entry(6).complete
    assert plan.entry(4).slim_below_zoom == 3 and plan.entry(5).slim_below_zoom is None


@pytest.mark.parametrize(
    "bad, message",
    [
        ([{"res": 5, "fill": "land", "zooms": [2, 4]}, {"res": 4, "fill": "land", "zooms": [5, 7]}], "ascending"),
        ([{"res": 4, "fill": "children", "parent": 3, "zooms": [2, 4]}], "first entry"),
        ([{"res": 4, "fill": "land", "zooms": [2, 4]}, {"res": 6, "fill": "children", "parent": 5, "where": {"urban": "centre"}, "zooms": [5, 7]}], "parent"),
        ([{"res": 4, "fill": "land", "zooms": [2, 5]}, {"res": 5, "fill": "land", "zooms": [5, 7]}], "overlap"),
        ([{"res": 4, "fill": "land", "zooms": [2, 4]}, {"res": 5, "fill": "children", "parent": 4, "where": {"urban": "town"}, "zooms": [5, 7]}], "urban"),
        ([{"res": 11, "fill": "land", "zooms": [2, 4]}], "between 4 and 10"),
        ([{"res": 4, "fill": "land", "zooms": [2, 4]}, {"res": 5, "fill": "children", "parent": 4, "zooms": [5, 7]}], "where"),
    ],
)
def test_plan_validation_speaks_plain_english(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        resplan.load_plan(_write(tmp_path, bad))


def test_missing_plan_file_is_a_plain_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="resolution plan"):
        resplan.load_plan(tmp_path / "nope.yaml")


def test_real_and_fixture_plans_are_valid():
    root = Path(__file__).resolve().parents[1]
    real = resplan.load_plan(root / "pipeline" / "resolution_plan.yaml")
    assert real.resolutions() == [4, 5, 6, 7]
    assert "US" in real.entry(6).where["countries"] and real.entry(7).where == {"urban": "centre"}
    fixture = resplan.load_plan(root / "pipeline" / "fixtures" / "resolution_plan.yaml")
    assert fixture.entry(6).where["countries"] == ["XA"]
    assert [e.zooms for e in fixture.entries] == [e.zooms for e in real.entries]


def test_settings_default_res_comes_from_the_plan(settings):
    assert settings.res == [4]  # conftest passes res=[4]
    fresh = Settings(root=settings.root, fixtures=True)
    assert fresh.res == fresh.plan.resolutions() == [4, 5, 6, 7]
    assert fresh.plan_path.name == "resolution_plan.yaml" and "fixtures" in str(fresh.plan_path)
    assert fresh.urban_path.name == "urban.parquet"
