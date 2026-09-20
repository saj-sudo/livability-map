from __future__ import annotations

from pipeline.stages import fetch


def test_fetch_copies_fixture_sources_and_is_idempotent(settings):
    first = fetch.run(settings)
    ok = [r for r in first if r.status == "ok"]
    assert ok, "nothing fetched"
    assert (settings.raw_dir / "CHECKSUMS").exists()
    assert (settings.raw("natural_earth_land") / "land.gpkg").exists()
    second = fetch.run(settings)
    assert all(r.status in ("cached", "refused") for r in second), [r for r in second if r.status not in ("cached", "refused")]


def test_fetch_refuses_unverified_license(settings):
    results = fetch.run(settings, only=["unverified_example"])
    assert len(results) == 1
    assert results[0].status == "refused"
    assert "VERIFY" in results[0].detail
    assert not (settings.raw("unverified_example") / "whr.csv").exists()


def test_lfs_pointer_is_rejected(tmp_path):
    p = tmp_path / "pointer"
    p.write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n")
    assert fetch.is_lfs_pointer(p)
    q = tmp_path / "real"
    q.write_bytes(b"GPKG" * 10)
    assert not fetch.is_lfs_pointer(q)
