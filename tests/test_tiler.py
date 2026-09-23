from __future__ import annotations

import gzip
import json

import h3
import mapbox_vector_tile
import numpy as np
import pytest
from pmtiles.reader import MmapSource, Reader
from pmtiles.tile import Compression, TileType

from pipeline import attrs, manifest, tiler
from pipeline.registry import load_dimensions
from pipeline.stages import admin, dims, export, fetch, grid, hazards, pop, score, tiles, urban


def _run_all(settings):
    fetch.run(settings)
    urban.run(settings)
    grid.run(settings)
    pop.run(settings)
    admin.run(settings)
    hazards.run(settings)
    dims.run(settings)
    score.run(settings)
    export.run(settings)


def test_split_antimeridian_yields_two_parts():
    ring = [(179.9, 10.0), (-179.9, 10.0), (-179.9, 10.2), (179.9, 10.2)]
    parts = tiler.split_antimeridian(ring)
    assert len(parts) == 2 and all(p.bounds[0] >= -180 and p.bounds[2] <= 180 for p in parts)


def test_world_fraction_and_tile_assignment():
    x, y = tiler.project_unit(np.array([0.0, 180.0]), np.array([0.0, 85.0511]))
    assert np.allclose(x, [0.5, 1.0]) and np.allclose(y, [0.5, 0.0], atol=1e-5)
    bboxes = np.array([[0.49, 0.49, 0.51, 0.51]])  # straddles the four central tiles at z1
    assign = tiler.assign_tiles(bboxes, 1)
    assert set(assign) == {(0, 0), (1, 0), (0, 1), (1, 1)}
    assert tiler.lnglat_to_tile(13.0, 42.5, 5) == (17, 11)


def test_cell_rings_handle_antimeridian_and_pole():
    cross = h3.latlng_to_cell(0.0, 179.995, 4)
    rings = tiler.cell_rings([cross])
    assert len(rings.row_of) == 2
    bb = tiler.ring_bboxes(rings)
    assert (bb[:, 2] > 1 - 1e-3).any() and (bb[:, 0] < 1e-3).any()  # one copy east of x=1, one at x~0
    polar = h3.latlng_to_cell(-89.0, 0.0, 4)
    assert len(tiler.cell_rings([polar]).row_of) == 0
    near = h3.latlng_to_cell(84.9, 0.0, 4)
    assert (tiler.cell_rings([near]).coords[:, 1] >= 0).all()


def test_column_store_yields_native_scalars_and_drops_missing(tmp_path):
    import pandas as pd

    df = pd.DataFrame({"a": pd.array([1, None, 3], dtype="Int16"), "b": [0.12345, np.nan, 2.0], "c": [True, False, True], "d": ["x", None, "z"]})
    cols = tiler.column_store(df, ["a", "b", "c", "d", "absent"])
    assert set(cols) == {"a", "b", "c", "d"}
    assert cols["d"][0] == "str" and cols["d"][3] == ["x", "z"]  # categorical codes + categories
    assert cols["c"][2] is None  # no missing values -> no mask
    props = tiler.props_for_rows(cols, ["a", "b", "c", "d"], np.array([0, 1, 2]))
    assert props == [{"a": 1, "b": 0.123, "c": True, "d": "x"}, {"c": False}, {"a": 3, "b": 2.0, "c": True, "d": "z"}]
    assert type(props[0]["a"]) is int and type(props[0]["b"]) is float and type(props[0]["c"]) is bool
    json.dumps(props)


def test_build_pmtiles_round_trips_fixture_hexes(settings):
    _run_all(settings)
    dims_reg = load_dimensions(settings.dimensions_path)
    out = settings.out_dir / "hexes.pmtiles"
    spec = tiler.LayerSpec("hex4", settings.out_dir / "hexes_r4.parquet", 2, 5, tuple(attrs.tile_attrs(dims_reg)), tuple(attrs.style_attrs(dims_reg)), 3)
    report = tiler.build_pmtiles([spec], out, workers=0)
    assert report.tiles > 0 and out.stat().st_size == report.bytes and report.sha256
    with open(out, "rb") as fh:
        r = Reader(MmapSource(fh))
        h = r.header()
        assert h["min_zoom"] == 2 and h["max_zoom"] == 5 and h["tile_type"] == TileType.MVT and h["tile_compression"] == Compression.GZIP
        assert h["clustered"] is True
        meta = json.loads(r.metadata()) if isinstance(r.metadata(), (str, bytes)) else r.metadata()
        assert meta["vector_layers"][0]["id"] == "hex4" and meta["vector_layers"][0]["fields"]["bivar"] == "Number"
        x, y = tiler.lnglat_to_tile(13.0, 42.5, 5)
        tile = mapbox_vector_tile.decode(gzip.decompress(r.get(5, x, y)))
        slim_x, slim_y = tiler.lnglat_to_tile(13.0, 42.5, 2)
        slim = mapbox_vector_tile.decode(gzip.decompress(r.get(2, slim_x, slim_y)))
    feats = tile["hex4"]["features"]
    props = {f["properties"]["h3"]: f["properties"] for f in feats}
    cedar = props[h3.latlng_to_cell(42.5, 13.0, 4)]
    assert cedar["inhabited"] is True and 0 <= cedar["heat_score"] <= 100
    assert "lat" not in cedar and "wb_src" not in cedar and "wb_lbl" not in cedar
    assert all(v is not None for f in feats for v in f["properties"].values())
    for f in feats:  # buffer keeps coordinates near the tile, never wildly outside
        for ring in f["geometry"]["coordinates"]:
            arr = np.asarray(ring)
            assert arr.min() >= -tiler.BUFFER - 1 and arr.max() <= tiler.EXTENT + tiler.BUFFER + 1
    slim_props = slim["hex4"]["features"][0]["properties"]
    assert "h3" not in slim_props and "bivar" in slim_props and "heat_days" not in slim_props
    # determinism: a rebuild is byte-identical
    report2 = tiler.build_pmtiles([spec], settings.out_dir / "again.pmtiles", workers=0)
    assert report2.sha256 == report.sha256


def test_tiles_stage_updates_manifest(settings):
    _run_all(settings)
    info = tiles.run(settings, backend="python", workers=0)
    m = json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["tiles"]["hexes"]["sha256"] == info["hexes"]["sha256"] and m["tiles"]["hexes"]["layers"][0]["name"] == "hex4"
    assert m["tiles"]["hexes"]["minzoom"] == 2 and m["tiles"]["hexes"]["maxzoom"] == 4  # the plan's res-4 zooms
    with pytest.raises(RuntimeError, match="tippecanoe"):
        tiles.run(settings, backend="tippecanoe")


def test_only_res4_still_overzooms(settings):
    _run_all(settings)
    tiles.run(settings, backend="python", workers=0)
    L = manifest.load(settings)["tiles"]["hexes"]["layers"]
    assert len(L) == 1 and L[0]["overzoom"] is True and L[0]["complete"] is True and L[0]["res"] == 4


def test_tiles_without_a_plan_in_the_manifest_is_a_plain_error(settings):
    _run_all(settings)
    m = manifest.load(settings)
    m.pop("resolution_plan")
    manifest.write(settings, m)
    with pytest.raises(FileNotFoundError, match="run `export` first"):
        tiles.run(settings, backend="python", workers=0)


def _features(settings, archive, z, lng, lat, layer):
    x, y = tiler.lnglat_to_tile(lng, lat, z)
    with open(settings.out_dir / archive, "rb") as fh:
        data = Reader(MmapSource(fh)).get(z, x, y)
    return mapbox_vector_tile.decode(gzip.decompress(data))[layer]["features"]


def test_tiles_build_one_archive_per_plan_entry(settings):
    settings.res = [4, 5, 6, 7]
    _run_all(settings)
    tiles.run(settings, backend="python", workers=0)
    m = manifest.load(settings)
    assert set(m["tiles"]) == {"hexes", "hexes_nbhd", "hexes_city"}
    fine = {L["name"]: L for a in ("hexes_nbhd", "hexes_city") for L in m["tiles"][a]["layers"]}
    assert fine["hex6"]["minzoom"] == 8 and fine["hex6"]["maxzoom"] == 9 and fine["hex6"]["res"] == 6
    assert fine["hex7"]["overzoom"] is True and fine["hex6"]["overzoom"] is True and fine["hex6"]["complete"] is False
    coarse = {L["name"]: L for L in m["tiles"]["hexes"]["layers"]}
    assert coarse["hex5"]["overzoom"] is True and coarse["hex4"]["overzoom"] is False and coarse["hex4"]["complete"] is True
    assert m["tiles"]["hexes_nbhd"]["maxzoom"] == 9 and [L["name"] for L in m["tiles"]["hexes_nbhd"]["layers"]] == ["hex6"]
    assert m["tiles"]["hexes_city"]["minzoom"] == 10 and m["tiles"]["hexes_city"]["maxzoom"] == 13
    assert (settings.out_dir / "hexes_nbhd.pmtiles").stat().st_size > 1000
    # the z7 tile over Alder carries hex5 features with ref true; the z10 tile carries hex7 features without ref
    assert any(f["properties"].get("ref") is True for f in _features(settings, "hexes.pmtiles", 7, 11.0, 43.0, "hex5"))
    assert all("ref" not in f["properties"] for f in _features(settings, "hexes_city.pmtiles", 10, 11.0, 43.0, "hex7"))


def test_tiles_archive_option_builds_one_archive(settings, capsys):
    settings.res = [4, 5, 6, 7]
    _run_all(settings)
    info = tiles.run(settings, backend="python", workers=0, archive="hexes_nbhd")
    assert set(info) == {"hexes_nbhd"} and (settings.out_dir / "hexes_nbhd.pmtiles").exists()
    assert not (settings.out_dir / "hexes.pmtiles").exists()


def test_a_subset_run_keeps_every_archive(settings):
    # final review I2: adding res 6/7 with `--res 6 --res 7` must not drop hexes.pmtiles from the manifest
    settings.res = [4, 5, 6, 7]
    _run_all(settings)
    tiles.run(settings, backend="python", workers=0)
    settings.res = [6, 7]
    export.run(settings)
    tiles.run(settings, backend="python", workers=0)
    m = manifest.load(settings)
    assert set(m["tiles"]) == {"hexes", "hexes_nbhd", "hexes_city"}
    assert [L["name"] for L in m["tiles"]["hexes"]["layers"]] == ["hex4", "hex5"]
