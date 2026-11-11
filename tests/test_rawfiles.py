from __future__ import annotations

import zipfile

import pytest

from pipeline import rawfiles
from pipeline.registry import Source


def _zip(path, members: dict[str, bytes]):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def _source(sid="src", fmt="geotiff-zip", files=("a.zip",), **extra) -> Source:
    return Source(id=sid, name="", group="life", access="direct", url="x", format=fmt, license="ok", files=list(files), extra=dict(extra))


@pytest.fixture()
def raw(settings, tmp_path, monkeypatch):
    """Raw files live in tmp_path/<source id>; unzipped copies go to the settings cache dir."""
    monkeypatch.setattr(settings, "raw", lambda sid: tmp_path / "raw" / sid)
    (tmp_path / "raw" / "src").mkdir(parents=True)
    return tmp_path / "raw" / "src"


def test_pick_member_uses_the_configured_one_or_the_only_match(tmp_path):
    arch = tmp_path / "a.zip"
    assert rawfiles._pick_member(["x/a.tif", "readme.txt"], None, rawfiles.RASTER_SUFFIXES, arch) == "x/a.tif"
    assert rawfiles._pick_member(["a.tif", "b.tif"], "b.tif", rawfiles.RASTER_SUFFIXES, arch) == "b.tif"
    with pytest.raises(FileNotFoundError, match="no member 'c.tif'"):
        rawfiles._pick_member(["a.tif"], "c.tif", rawfiles.RASTER_SUFFIXES, arch)
    with pytest.raises(ValueError, match="found 2"):
        rawfiles._pick_member(["a.tif", "b.TIF"], None, rawfiles.RASTER_SUFFIXES, arch)
    with pytest.raises(ValueError, match="found 0"):
        rawfiles._pick_member(["readme.txt"], None, rawfiles.RASTER_SUFFIXES, arch)


def test_pick_member_ignores_macos_resource_forks(tmp_path):
    names = ["__MACOSX/._a.tif", "a.tif"]
    assert rawfiles._pick_member(names, None, rawfiles.RASTER_SUFFIXES, tmp_path / "a.zip") == "a.tif"


def test_unzip_member_extracts_once_and_repairs_a_truncated_copy(tmp_path):
    arch = _zip(tmp_path / "a.zip", {"deep/a.tif": b"0123456789"})
    dest = tmp_path / "out"
    target = rawfiles.unzip_member(arch, dest, "deep/a.tif")
    assert target == dest / "deep" / "a.tif" and target.read_bytes() == b"0123456789"
    target.write_bytes(b"01234")  # a copy cut short by a crash
    assert rawfiles.unzip_member(arch, dest, "deep/a.tif").read_bytes() == b"0123456789"
    mtime = target.stat().st_mtime_ns
    rawfiles.unzip_member(arch, dest, "deep/a.tif")
    assert target.stat().st_mtime_ns == mtime  # same size: left alone
    assert [p.name for p in target.parent.iterdir()] == ["a.tif"]  # no temp file left behind


def test_unzip_prefix_extracts_a_directory_once(tmp_path):
    arch = _zip(tmp_path / "a.zip", {"d.gdb/a": b"1", "d.gdb/b": b"2", "other/c": b"3"})
    dest = tmp_path / "out"
    gdb = rawfiles.unzip_prefix(arch, dest, "d.gdb")
    assert sorted(p.name for p in gdb.iterdir()) == [".extracted", "a", "b"]
    assert not (dest / "other").exists()
    (gdb / "a").write_bytes(b"changed")
    rawfiles.unzip_prefix(arch, dest, "d.gdb")
    assert (gdb / "a").read_bytes() == b"changed"  # the marker stops a second extraction


def test_unzip_prefix_refuses_a_prefix_nothing_matches(tmp_path):
    arch = _zip(tmp_path / "a.zip", {"x/a": b"1"})
    with pytest.raises(FileNotFoundError, match="no members under 'nope.gdb'"):
        rawfiles.unzip_prefix(arch, tmp_path / "out", "nope.gdb")


def test_resolve_raster_unzips_a_zip_and_passes_a_plain_file_through(settings, raw):
    _zip(raw / "a.zip", {"inner/a.tif": b"tiff"})
    path = rawfiles.resolve_raster(settings, _source())
    assert path.read_bytes() == b"tiff" and path.is_relative_to(settings.cache_dir / "unzipped" / "src")
    (raw / "plain.tif").write_bytes(b"x")
    assert rawfiles.resolve_raster(settings, _source(fmt="geotiff", files=("plain.tif",))) == raw / "plain.tif"


def test_resolve_raster_says_when_the_download_is_missing(settings, raw):
    with pytest.raises(FileNotFoundError, match="not downloaded yet"):
        rawfiles.resolve_raster(settings, _source())


def test_resolve_vector_forms(settings, raw):
    _zip(raw / "one.zip", {"a.shp": b"", "a.dbf": b""})
    _zip(raw / "two.zip", {"a.shp": b"", "b.shp": b""})
    (raw / "plain.gpkg").write_bytes(b"x")
    one = rawfiles.resolve_vector(settings, _source(fmt="shapefile-zip", files=("one.zip",)))
    assert one == f"zip://{(raw / 'one.zip').as_posix()}!a.shp"  # the only .shp is picked
    two = rawfiles.resolve_vector(settings, _source(fmt="shapefile-zip", files=("two.zip",)))
    assert two == f"zip://{(raw / 'two.zip').as_posix()}"  # ambiguous: the whole archive
    named = rawfiles.resolve_vector(settings, _source(fmt="shapefile-zip", files=("two.zip",), member="b.shp"))
    assert named.endswith("!b.shp")
    assert rawfiles.resolve_vector(settings, _source(fmt="geopackage", files=("plain.gpkg",))) == str(raw / "plain.gpkg")


def test_resolve_vector_filegdb_needs_gdb_member_and_extracts_it(settings, raw):
    _zip(raw / "a.zip", {"d.gdb/a": b"1"})
    with pytest.raises(ValueError, match="gdb_member"):
        rawfiles.resolve_vector(settings, _source(fmt="filegdb-zip"))
    path = rawfiles.resolve_vector(settings, _source(fmt="filegdb-zip", gdb_member="d.gdb/"))
    assert (settings.cache_dir / "unzipped" / "src" / "d.gdb" / "a").read_bytes() == b"1" and path.endswith("d.gdb")
