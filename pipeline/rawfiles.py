"""Locate the file a stage should open for a source, extracting zip archives once (SPEC §11).

Real downloads are often zipped (GHSL GeoTIFF, Aqueduct 4.0 File Geodatabase, Census shapefiles).
rasterio and GDAL can read inside zips through ``/vsizip/``, but windowed reads on a deflated
1 GB GeoTIFF are painfully slow, so rasters and File Geodatabases are extracted once into
``data/interim/unzipped/<source_id>/`` (gitignored) and reused. Shapefile and GeoPackage zips are
opened in place with a ``zip://archive!member`` path, which pyogrio handles natively.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from .config import Settings
from .registry import Source

RASTER_SUFFIXES = (".tif", ".tiff", ".nc")
VECTOR_SUFFIXES = (".shp", ".gpkg", ".geojson", ".fgb")


def _unzip_dir(settings: Settings, source: Source) -> Path:
    return settings.interim_dir / "unzipped" / source.id


def _pick_member(names: list[str], member: str | None, suffixes: tuple[str, ...], archive: Path) -> str:
    """The archive member to use: the configured one, or the only file with a matching suffix."""
    if member:
        if member not in names:
            raise FileNotFoundError(f"{archive.name} has no member {member!r}; members: {names[:20]}")
        return member
    candidates = [n for n in names if n.lower().endswith(suffixes) and not n.startswith("__MACOSX")]
    if len(candidates) != 1:
        raise ValueError(
            f"{archive.name}: expected exactly one {suffixes} member, found {len(candidates)}: "
            f"{candidates[:10]}. Set `member:` on the source in sources.yaml."
        )
    return candidates[0]


def unzip_member(archive: Path, dest_dir: Path, member: str) -> Path:
    """Extract one member (kept under its archive path) unless a same-size extracted copy exists."""
    target = dest_dir / member
    with zipfile.ZipFile(archive) as z:
        info = z.getinfo(member)
        if target.exists() and target.stat().st_size == info.file_size:
            return target
        dest_dir.mkdir(parents=True, exist_ok=True)
        z.extract(member, dest_dir)
    return target


def unzip_prefix(archive: Path, dest_dir: Path, prefix: str) -> Path:
    """Extract every member under ``prefix`` (a directory such as a File Geodatabase) once."""
    target = dest_dir / prefix
    marker = target / ".extracted"
    if marker.exists():
        return target
    with zipfile.ZipFile(archive) as z:
        members = [n for n in z.namelist() if n.startswith(prefix)]
        if not members:
            raise FileNotFoundError(f"{archive.name} has no members under {prefix!r}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        z.extractall(dest_dir, members=members)
    target.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok", encoding="utf-8")
    return target


def resolve_raster(settings: Settings, source: Source, index: int = 0) -> Path:
    """Path of the raster to open: the raw file, or the extracted member of a ``*-zip`` download."""
    raw = settings.raw(source.id) / source.files[index]
    if not raw.exists():
        raise FileNotFoundError(f"{source.id}: {raw} is not downloaded yet (run `fetch` first)")
    if source.format.endswith("-zip") or raw.suffix.lower() == ".zip":
        with zipfile.ZipFile(raw) as z:
            member = _pick_member(z.namelist(), source.extra.get("member"), RASTER_SUFFIXES, raw)
        return unzip_member(raw, _unzip_dir(settings, source), member)
    return raw


def resolve_vector(settings: Settings, source: Source, index: int = 0) -> str:
    """A path GDAL/pyogrio can open for a vector source: plain file, ``zip://archive!member``
    for shapefile / GeoPackage zips, or the extracted ``.gdb`` directory for File Geodatabases
    (``format: filegdb-zip`` with ``gdb_member`` on the source)."""
    raw = settings.raw(source.id) / source.files[index]
    if not raw.exists():
        raise FileNotFoundError(f"{source.id}: {raw} is not downloaded yet (run `fetch` first)")
    if source.format == "filegdb-zip":
        prefix = source.extra.get("gdb_member")
        if not prefix:
            raise ValueError(f"{source.id}: filegdb-zip sources need `gdb_member` (path of the .gdb inside the zip)")
        return str(unzip_prefix(raw, _unzip_dir(settings, source), prefix.rstrip("/")))
    if raw.suffix.lower() == ".zip":
        with zipfile.ZipFile(raw) as z:
            names = z.namelist()
        member = source.extra.get("member")
        if not member:
            candidates = [n for n in names if n.lower().endswith(VECTOR_SUFFIXES) and not n.startswith("__MACOSX")]
            member = candidates[0] if len(candidates) == 1 else None
        return f"zip://{raw.as_posix()}!{member}" if member else f"zip://{raw.as_posix()}"
    return str(raw)
