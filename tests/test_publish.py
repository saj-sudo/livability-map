from __future__ import annotations

import json

import pytest

from pipeline.stages import (
    admin,
    dims,
    export,
    fetch,
    grid,
    hazards,
    pop,
    publish,
    score,
    tiles,
    urban,
)


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
    tiles.run(settings, backend="python", workers=0)


def test_publish_local_copies_files_and_stamps_manifest(settings, tmp_path):
    _run_all(settings)
    dest = tmp_path / "webdata"
    info = publish.run(settings, target="local", local_dir=dest)
    assert info["target"] == "local" and (dest / "hexes.pmtiles").exists()
    m = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert m["publish_target"] == "local" and m["published_at"] and m["public_base_url"] == "/data"
    assert m["tiles"]["hexes"]["key"] == "hexes.pmtiles"


def test_publish_refuses_unconfirmed_sources(settings, tmp_path, monkeypatch):
    _run_all(settings)
    monkeypatch.setattr(publish, "unverified_sources", lambda s: ["whr_ladder"])
    with pytest.raises(RuntimeError, match="whr_ladder"):
        publish.run(settings, target="local", local_dir=tmp_path / "x")


def test_publish_r2_uploads_sets_cors_and_checks_ranges(settings, monkeypatch):
    _run_all(settings)
    calls = []

    class FakeClient:
        def upload_file(self, path, bucket, key, ExtraArgs=None):
            calls.append(("upload", bucket, key, ExtraArgs["ContentType"]))

        def put_bucket_cors(self, Bucket, CORSConfiguration):
            calls.append(("cors", Bucket, CORSConfiguration["CORSRules"][0]["AllowedOrigins"]))

    monkeypatch.setattr(publish, "_env", lambda root: {"R2_ACCOUNT_ID": "acc", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s", "R2_BUCKET": "tiles", "R2_PUBLIC_BASE_URL": "https://tiles.example.org/", "R2_ALLOWED_ORIGINS": "https://a.example, http://localhost:3000"})
    monkeypatch.setattr(publish, "_client", lambda env: FakeClient())
    monkeypatch.setattr(publish, "_range_check", lambda url: {"status": 206, "magic": True, "acao": "*", "cf_cache": "HIT", "content_range": "bytes 0-16383/1000000"})
    info = publish.run(settings, target="auto")
    assert info["target"] == "r2" and info["range_check"]["status"] == 206
    assert ("upload", "tiles", "hexes.pmtiles", "application/octet-stream") in calls
    assert ("upload", "tiles", "manifest.json", "application/json") in calls
    assert ("cors", "tiles", ["https://a.example", "http://localhost:3000"]) in calls
    m = json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["publish_target"] == "r2" and m["public_base_url"] == "https://tiles.example.org"


def test_diagnose_messages():
    assert publish._diagnose({"status": 200, "magic": True, "acao": "*", "cf_cache": "HIT"}).startswith("expected HTTP 206")
    assert "Hotlink" in publish._diagnose({"status": 206, "magic": True, "acao": None, "cf_cache": None})
    assert publish._diagnose({"status": 206, "magic": True, "acao": "*", "cf_cache": "HIT"}).startswith("ok")


def test_local_publish_ships_every_archive(settings, tmp_path):
    settings.res = [4, 5, 6, 7]
    _run_all(settings)
    dest = tmp_path / "data"
    publish.run(settings, target="local", local_dir=dest)
    assert {p.name for p in dest.iterdir()} == {"hexes.pmtiles", "hexes_fine.pmtiles", "manifest.json"}
    assert publish.files_to_ship(json.loads((dest / "manifest.json").read_text(encoding="utf-8"))) == ["manifest.json", "hexes.pmtiles", "hexes_fine.pmtiles"]
