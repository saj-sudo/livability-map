from __future__ import annotations

import json

import pandas as pd
from typer.testing import CliRunner

from pipeline import attrs
from pipeline.registry import load_dimensions
from pipeline.stages import admin, dims, export, fetch, grid, hazards, pop, score


def _run_all(settings):
    fetch.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)
    score.run(settings)
    export.run(settings)


def test_export_writes_parquet_and_manifest(settings):
    _run_all(settings)
    out = pd.read_parquet(settings.out_dir / "hexes_r4.parquet")
    keep = attrs.tile_attrs(load_dimensions(settings.dimensions_path))
    assert set(keep) <= set(out.columns)
    assert str(out["heat_score"].dtype) == "Int16" and out["inhabited"].dtype == bool
    m = json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["scenario"] == "rcp45_ssp245" and m["non_commercial"] is True and m["h3_res"] == [4]
    ids = {s["id"] for s in m["sources"]}
    assert {"cckp_hd35", "gdl_shdi", "whr_ladder"} <= ids
    wb = next(d for d in m["dimensions"] if d["id"] == "wb")
    assert wb["coverage"]["4"]["admin1"] > 0 and wb["scale"] == "minmax"
    assert m["coverage_summary"]["4"]["hexes_total"] == len(out)
    assert m["coverage_summary"]["4"]["share_inhabited_coverage4"] is not None
    assert any("0.15" in n for n in m["processing_notes"])
    spot = next(s for s in m["spot_checks"]["4"] if s["name"].startswith("Alder"))
    assert spot["found"] and spot["inhabited"] is True and "heat_days" in spot
    assert "pol" in m["known_gaps"]["4"] and "XA" in m["known_gaps"]["4"]["pol"]["countries_without_data"]


def test_export_geojsonl_has_tile_attrs_only(settings):
    _run_all(settings)
    export.run(settings, geojson=True)
    line = json.loads((settings.out_dir / "hexes_r4.geojsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["geometry"]["type"] == "Polygon"
    props = line["properties"]
    assert "lat" not in props and "wb_src" not in props and "h3" in props
    assert all(v is not None for v in props.values())


def test_all_runs_through_export_on_fixtures(settings):
    from pipeline.__main__ import app

    result = CliRunner().invoke(app, ["--fixtures", "--res", "4", "--root", str(settings.root), "all"])
    assert result.exit_code == 0, result.output
    assert "export res 4" in result.output and "export manifest" in result.output
    assert "stopped before 'tiles'" in result.output
