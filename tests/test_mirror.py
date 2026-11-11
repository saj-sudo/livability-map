from __future__ import annotations

import shutil

import pytest

from pipeline import checksums, mirror
from pipeline.registry import Source
from pipeline.stages import fetch


class Missing(Exception):
    response = {"Error": {"Code": "404"}}


class FakeR2:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.uploads: list[str] = []

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise Missing(Key)
        return {"ContentLength": len(self.objects[Key])}

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.uploads.append(key)
        self.objects[key] = open(path, "rb").read()

    def download_file(self, bucket, key, path):
        with open(path, "wb") as fh:
            fh.write(self.objects[key])


def _record(settings, sid, fname, body: bytes) -> str:
    path = settings.raw(sid) / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    digest = checksums.sha256_of(path)
    checksums.write_checksums(settings.raw_dir / "CHECKSUMS", {**checksums.read_checksums(settings.raw_dir / "CHECKSUMS"), (sid, fname): digest})
    return digest


def test_push_uploads_each_recorded_file_once_by_digest(settings):
    r2 = FakeR2()
    m = mirror.Mirror(r2, "raw")
    d1 = _record(settings, "src_a", "a.csv", b"alpha\n")
    _record(settings, "src_b", "b.tif", b"beta\n")
    counts = mirror.push_all(settings, m)
    assert counts == {"uploaded": 2, "held": 0, "missing": 0, "changed": 0}
    assert mirror.key(d1) in r2.objects and r2.objects[mirror.key(d1)] == b"alpha\n"
    assert mirror.push_all(settings, m)["held"] == 2 and len(r2.uploads) == 2
    (settings.raw("src_a") / "a.csv").write_bytes(b"edited\n")  # differs from CHECKSUMS: never mirrored
    shutil.rmtree(settings.raw("src_b"))
    assert mirror.push_all(settings, m) == {"uploaded": 0, "held": 0, "missing": 1, "changed": 1}
    assert mirror.missing_from(settings, mirror.Mirror(FakeR2(), "raw")) == ["src_a/a.csv", "src_b/b.tif"]


def _source(sid, access="direct"):
    return Source(id=sid, name=sid, group="reference", access=access, url="https://example.org/x/" if access == "direct" else None, format="csv", license="CC BY 4.0", files=["f.csv"], extra={"verified": "confirmed"})


@pytest.mark.parametrize("access", ["direct", "manual"])
def test_fetch_restores_a_missing_recorded_file_from_the_mirror(settings, monkeypatch, access):
    r2 = FakeR2()
    m = mirror.Mirror(r2, "raw")
    digest = _record(settings, "gone", "f.csv", b"the bytes the map was built from\n")
    m.push(settings.raw("gone") / "f.csv", digest, "gone", "f.csv")
    shutil.rmtree(settings.raw("gone"))  # a clean machine
    monkeypatch.setattr(fetch, "_download", lambda *a: pytest.fail("went upstream although the mirror holds the file"))
    [r] = fetch.fetch_source(_source("gone", access), settings, {("gone", "f.csv"): digest}, m)
    assert r.status == "ok" and "raw mirror" in r.detail
    assert (settings.raw("gone") / "f.csv").read_bytes() == b"the bytes the map was built from\n"


def test_a_moved_upstream_file_is_replaced_by_the_mirrored_bytes(settings, monkeypatch):
    r2 = FakeR2()
    m = mirror.Mirror(r2, "raw")
    digest = _record(settings, "moved", "f.csv", b"v1\n")
    m.push(settings.raw("moved") / "f.csv", digest, "moved", "f.csv")
    (settings.raw("moved") / "f.csv").write_bytes(b"v2 from upstream\n")
    monkeypatch.setattr(fetch, "_download", lambda *a: pytest.fail("went upstream"))
    [r] = fetch.fetch_source(_source("moved"), settings, {("moved", "f.csv"): digest}, m)
    assert r.status == "ok" and (settings.raw("moved") / "f.csv").read_bytes() == b"v1\n"


def test_corrupt_mirror_bytes_are_ignored_and_upstream_is_tried(settings, monkeypatch):
    r2 = FakeR2()
    m = mirror.Mirror(r2, "raw")
    digest = _record(settings, "bad", "f.csv", b"good\n")
    r2.objects[mirror.key(digest)] = b"rotten\n"
    shutil.rmtree(settings.raw("bad"))
    called = []

    def upstream(url, dest, root):
        called.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(b"good\n")
        return tmp

    monkeypatch.setattr(fetch, "_download", upstream)
    [r] = fetch.fetch_source(_source("bad"), settings, {("bad", "f.csv"): digest}, m)
    assert called and r.status == "ok" and (settings.raw("bad") / "f.csv").read_bytes() == b"good\n"
    assert not list(settings.raw("bad").glob("*.part"))


def test_the_mirror_refuses_the_public_tiles_bucket(settings, monkeypatch):
    monkeypatch.setattr(mirror, "read_env", lambda root: {"R2_RAW_BUCKET": "tiles", "R2_BUCKET": "tiles"})
    settings.fixtures = False
    try:
        with pytest.raises(RuntimeError, match="separate, private bucket"):
            mirror.from_env(settings)
    finally:
        settings.fixtures = True
    assert mirror.from_env(settings) is None  # fixture runs never use it
