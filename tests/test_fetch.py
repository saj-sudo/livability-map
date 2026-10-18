from __future__ import annotations

from pipeline.stages import fetch


def test_fetch_copies_fixture_sources_and_is_idempotent(settings):
    first = fetch.run(settings)
    ok = [r for r in first if r.status == "ok"]
    assert ok, "nothing fetched"
    assert (settings.raw_dir / "CHECKSUMS").exists()
    assert (settings.raw("natural_earth_land") / "land.gpkg").exists()
    second = fetch.run(settings)
    assert all(r.status in ("cached", "refused", "missing") for r in second), [r for r in second if r.status not in ("cached", "refused", "missing")]


def test_fetch_dataverse_without_env_is_missing_with_recipe(settings, capsys, monkeypatch):
    for k in ("NAME", "EMAIL", "INSTITUTION", "POSITION"):
        monkeypatch.delenv(f"DATAVERSE_GUESTBOOK_{k}", raising=False)
    results = fetch.run(settings, only=["dataverse_example"])
    assert len(results) == 1 and results[0].status == "missing" and ".env" in results[0].detail
    assert "download the file by hand" in capsys.readouterr().out


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


def _direct_source(sid: str = "drift_example"):
    from pipeline.registry import Source

    return Source(id=sid, name="drift", group="reference", access="direct", url="https://example.org/data/", format="csv", license="CC BY 4.0", files=["a.csv"], extra={"verified": "confirmed"})


def test_moved_vintage_never_replaces_the_verified_file(settings, monkeypatch):
    src = _direct_source()
    dest = settings.raw(src.id) / "a.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("old,verified\n", encoding="utf-8")
    checksums = {(src.id, "a.csv"): "0" * 64}  # recorded digest differs from what is on disk -> re-download

    def fake_download(url, d, root):
        tmp = d.with_suffix(d.suffix + ".part")
        tmp.write_text("new,vintage\n", encoding="utf-8")
        return tmp

    monkeypatch.setattr(fetch, "_download", fake_download)
    [r] = fetch.fetch_source(src, settings, checksums)
    assert r.status == "error" and "checksum changed" in r.detail and "a.csv.new" in r.detail
    assert dest.read_text(encoding="utf-8") == "old,verified\n"
    assert (dest.parent / "a.csv.new").read_text(encoding="utf-8") == "new,vintage\n"
    assert checksums[(src.id, "a.csv")] == "0" * 64  # not overwritten


def test_first_download_is_recorded_and_moved_into_place(settings, monkeypatch):
    src = _direct_source("fresh_example")
    dest = settings.raw(src.id) / "a.csv"

    def fake_download(url, d, root):
        d.parent.mkdir(parents=True, exist_ok=True)
        tmp = d.with_suffix(d.suffix + ".part")
        tmp.write_text("x\n", encoding="utf-8")
        return tmp

    monkeypatch.setattr(fetch, "_download", fake_download)
    checksums: dict = {}
    [r] = fetch.fetch_source(src, settings, checksums)
    assert r.status == "ok" and dest.read_text(encoding="utf-8") == "x\n"
    assert checksums[(src.id, "a.csv")] == fetch.sha256_of(dest)
    assert not dest.with_suffix(".csv.part").exists()


def test_replaced_manual_file_is_accepted_but_announced(settings):
    from pipeline.registry import Source

    src = Source(id="manual_example", name="m", group="wellbeing", access="manual", url=None, format="csv", license="CC BY 4.0", files=["m.csv"], extra={"verified": "confirmed"})
    dest = settings.raw(src.id) / "m.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("v2\n", encoding="utf-8")
    checksums = {(src.id, "m.csv"): "f" * 64}
    [r] = fetch.fetch_source(src, settings, checksums)
    assert r.status == "ok" and "REPLACES recorded ffffffffffff" in r.detail
    assert checksums[(src.id, "m.csv")] == fetch.sha256_of(dest)
