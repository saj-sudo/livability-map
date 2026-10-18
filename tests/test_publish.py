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


R2_ENV = {"R2_ACCOUNT_ID": "acc", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s", "R2_BUCKET": "tiles", "R2_PUBLIC_BASE_URL": "https://tiles.example.org/", "R2_ALLOWED_ORIGINS": "https://a.example, http://localhost:3000"}
RANGE_OK = {"status": 206, "magic": True, "acao": "*", "cf_cache": "HIT", "content_range": "bytes 0-16383/1000000"}


class FakeBucket:
    def __init__(self):
        self.calls: list[tuple] = []
        self.objects: dict[str, bytes] = {}

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.calls.append(("upload", bucket, key, ExtraArgs["ContentType"], ExtraArgs["CacheControl"]))
        self.objects[key] = open(path, "rb").read()

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"ContentLength": len(self.objects[Key])}

    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self.calls.append(("cors", Bucket, CORSConfiguration["CORSRules"][0]["AllowedOrigins"]))


def _as_release(monkeypatch, bucket, live=None, range_check=RANGE_OK, real=False):
    """Fake bucket and network; with ``real`` the fixture world stands in for a real whole-world
    build (the release-only checks are tested in test_validate.py)."""
    from pipeline.stages import validate

    if real:
        monkeypatch.setattr(publish, "_partial", lambda settings: False)
    monkeypatch.setattr(publish, "_env", lambda root: dict(R2_ENV))
    monkeypatch.setattr(publish, "_client", lambda env: bucket)
    monkeypatch.setattr(publish, "_range_check", lambda url: dict(range_check))
    monkeypatch.setattr(publish, "_live_manifest", lambda base: live)
    monkeypatch.setattr(validate, "_release", lambda settings, m: [])


def test_publish_r2_uploads_content_addressed_archives_then_the_manifest(settings, monkeypatch):
    _run_all(settings)
    bucket = FakeBucket()
    _as_release(monkeypatch, bucket, real=True)
    info = publish.run(settings, target="r2")
    sha = json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))["tiles"]["hexes"]["sha256"]
    key = f"hexes.{sha[:12]}.pmtiles"
    assert info["target"] == "r2" and info["keys"] == {"hexes": key}
    uploads = [c for c in bucket.calls if c[0] == "upload"]
    assert uploads[0] == ("upload", "tiles", key, "application/octet-stream", publish.ARCHIVE_CACHE)
    assert uploads[-1] == ("upload", "tiles", "manifest.json", "application/json", "no-cache")  # switched last
    assert any(c[2].startswith("manifests/") for c in uploads)
    assert ("cors", "tiles", ["https://a.example", "http://localhost:3000"]) in bucket.calls
    live = json.loads(bucket.objects["manifest.json"])
    assert live["tiles"]["hexes"]["key"] == key and live["publish_target"] == "r2" and live["public_base_url"] == "https://tiles.example.org"
    m = json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["tiles"]["hexes"]["key"] == "hexes.pmtiles"  # the local build keeps plain names
    # a second release of the same build re-uses the archive already in the bucket
    bucket.calls.clear()
    publish.run(settings, target="r2")
    assert [c[2] for c in bucket.calls if c[0] == "upload" and c[2].endswith(".pmtiles")] == []


def test_publish_r2_refuses_a_fixture_build(settings, monkeypatch):
    _run_all(settings)
    bucket = FakeBucket()
    _as_release(monkeypatch, bucket)
    with pytest.raises(RuntimeError, match="never goes to R2"):
        publish.run(settings, target="r2")
    assert bucket.calls == []


def test_publish_auto_keeps_a_fixture_build_local_even_with_r2_credentials(settings, monkeypatch, tmp_path, capsys):
    _run_all(settings)
    bucket = FakeBucket()
    _as_release(monkeypatch, bucket)
    info = publish.run(settings, target="auto", local_dir=tmp_path / "web")
    assert info["target"] == "local" and bucket.calls == []
    assert "never go to R2" in capsys.readouterr().out


def test_publish_r2_stops_before_the_manifest_when_ranges_fail(settings, monkeypatch):
    _run_all(settings)
    bucket = FakeBucket()
    _as_release(monkeypatch, bucket, range_check={"status": 200, "magic": True, "acao": "*", "cf_cache": "HIT", "content_range": None}, real=True)
    with pytest.raises(RuntimeError, match="before switching manifest.json"):
        publish.run(settings, target="r2")
    assert "manifest.json" not in bucket.objects


def test_publish_r2_refuses_a_coverage_collapse_against_the_live_build(settings, monkeypatch):
    _run_all(settings)
    live = json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))
    live["built_at"] = "2026-01-01T00:00:00+00:00"
    for d in live["dimensions"]:
        if d["id"] == "jobs":
            d["coverage"]["4"] = {k: v * 3 for k, v in d["coverage"]["4"].items()}  # the live build covered far more
    bucket = FakeBucket()
    _as_release(monkeypatch, bucket, live=live, real=True)
    with pytest.raises(ValueError, match="validate found"):
        publish.run(settings, target="r2")
    assert bucket.calls == []
    publish.run(settings, target="r2", max_drop=0.9)  # an explained drop goes through
    assert "manifest.json" in bucket.objects


def test_publish_refuses_tiles_older_than_the_export(settings, tmp_path):
    import os

    _run_all(settings)
    parquet = settings.out_dir / "hexes_r4.parquet"
    st = parquet.stat()
    os.utime(parquet, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))  # export ran again, tiles did not
    with pytest.raises(ValueError, match="run `tiles`"):
        publish.run(settings, target="local", local_dir=tmp_path / "x")


def test_diagnose_messages():
    assert publish._diagnose({"status": 200, "magic": True, "acao": "*", "cf_cache": "HIT"}).startswith("expected HTTP 206")
    assert "Hotlink" in publish._diagnose({"status": 206, "magic": True, "acao": None, "cf_cache": None})
    assert publish._diagnose({"status": 206, "magic": True, "acao": "*", "cf_cache": "HIT"}).startswith("ok")


def test_local_publish_ships_every_archive(settings, tmp_path):
    settings.res = [4, 5, 6, 7]
    _run_all(settings)
    dest = tmp_path / "data"
    publish.run(settings, target="local", local_dir=dest)
    assert {p.name for p in dest.iterdir()} == {"hexes.pmtiles", "hexes_nbhd.pmtiles", "hexes_city.pmtiles", "manifest.json"}
    assert publish.files_to_ship(json.loads((dest / "manifest.json").read_text(encoding="utf-8"))) == ["manifest.json", "hexes.pmtiles", "hexes_city.pmtiles", "hexes_nbhd.pmtiles"]


def test_local_publish_removes_archives_the_plan_no_longer_lists(settings, tmp_path):
    _run_all(settings)
    dest = tmp_path / "webdata"
    dest.mkdir()
    (dest / "hexes_fine.pmtiles").write_bytes(b"PMTiles old")  # an archive from an older plan
    (dest / "gazetteer.json").write_text("{}", encoding="utf-8")  # not ours to touch
    publish.run(settings, target="local", local_dir=dest)
    assert not (dest / "hexes_fine.pmtiles").exists()
    assert (dest / "gazetteer.json").exists() and (dest / "hexes.pmtiles").exists()
