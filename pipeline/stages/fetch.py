"""``fetch`` stage (SPEC §5, §6.2, §11, invariant 4).

Downloads every source in ``sources.yaml`` into ``data/raw/<id>/``, verifies sha256 against the
committed ``data/raw/CHECKSUMS``, and skips files whose checksum already matches.

Rules:
- A source whose license (or, for direct sources, URL) is still ``VERIFY`` is refused, loudly.
  Verify it, log it in SPEC §15, then fetch. Invariant 4.
- ``access: manual`` sources (Google Earth Engine export, registration-gated downloads) are not
  downloaded. The stage checks the files are present and prints the recipe if not.
- ``file://`` URLs (fixtures) are copied through the same checksum path as HTTP downloads.
- Redirects are followed and Git LFS pointer files are rejected (geoBoundaries, §15.7).
- With a raw mirror configured (``R2_RAW_BUCKET``, SPEC §13.41), a file whose checksum is recorded
  is restored from the mirror before going upstream: the exact bytes the map was built from.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ..checksums import CHUNK, read_checksums, sha256_of, write_checksums  # noqa: F401 - re-exported
from ..config import Settings
from ..registry import Source, load_sources

if TYPE_CHECKING:
    from ..mirror import Mirror

LFS_MAGIC = b"version https://git-lfs.github.com/spec/v1"


@dataclass
class FetchResult:
    source: str
    file: str
    status: str  # ok | cached | missing | refused | error
    detail: str = ""


def is_lfs_pointer(path: Path) -> bool:
    if path.stat().st_size > 1024:
        return False
    with open(path, "rb") as fh:
        return fh.read(len(LFS_MAGIC)) == LFS_MAGIC


def _resolve_file_url(url: str, root: Path) -> Path:
    parsed = urlparse(url)
    raw = parsed.netloc + parsed.path if parsed.netloc else parsed.path
    p = Path(raw)
    if not p.is_absolute():
        p = root / raw.lstrip("/") if raw.startswith("/") and not (root / raw).exists() else root / raw
    return p


def _download(url: str, dest: Path, root: Path) -> Path:
    """Download to ``<dest>.part`` and return that path; the caller checks the checksum before
    the file takes ``dest``'s place, so a moved vintage never replaces the verified one."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    if url.startswith("file://"):
        src = _resolve_file_url(url, root)
        if not src.exists():
            raise FileNotFoundError(src)
        shutil.copyfile(src, tmp)
    else:
        import requests

        headers = {"User-Agent": "livability-map pipeline (https://github.com/saj-sudo/livability-map)"}
        with requests.get(url, stream=True, allow_redirects=True, timeout=120, headers=headers) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(CHUNK):
                    fh.write(chunk)
    if tmp.stat().st_size == 0:
        tmp.unlink()
        raise RuntimeError("the server answered with an empty body (a bot check such as HUD's 202 challenge?); nothing was saved")
    if is_lfs_pointer(tmp):
        tmp.unlink()
        raise RuntimeError("downloaded a Git LFS pointer instead of the file; use a /raw/ URL that redirects to media.githubusercontent.com")
    return tmp


def dataverse_guestbook(root: Path) -> dict[str, str] | None:
    """Guestbook fields from ``.env`` (SPEC §13.26). None when any is missing: nothing is sent
    to Dataverse unless Saj filled all four in deliberately."""
    from dotenv import dotenv_values

    env = {**dotenv_values(root / ".env"), **os.environ}
    fields = {k: (env.get(f"DATAVERSE_GUESTBOOK_{k.upper()}") or "").strip() for k in ("name", "email", "institution", "position")}
    return fields if all(fields.values()) else None


def dataverse_signed_url(url: str, guest: dict[str, str]) -> str:
    """POST the guestbook response; Dataverse answers with a short-lived signed download URL."""
    import requests

    resp = requests.post(url, json={"guestbookResponse": guest}, timeout=60, headers={"User-Agent": "livability-map pipeline"})
    resp.raise_for_status()
    signed = (resp.json().get("data") or {}).get("signedUrl")
    if not signed:
        raise RuntimeError("Dataverse did not return a signed download URL; the guestbook flow may have changed (SPEC §15 medsl)")
    return signed


def _file_url_for(src: Source, fname: str) -> str:
    """Per-file URL: ``url`` may point at a directory (ends with '/') or a single file."""
    assert src.url
    if src.url.endswith("/"):
        return src.url + fname
    return src.url


def fetch_source(src: Source, settings: Settings, checksums: dict[tuple[str, str], str], mirror: Mirror | None = None) -> list[FetchResult]:
    results: list[FetchResult] = []
    dest_dir = settings.raw(src.id)

    if src.unverified:
        results.append(FetchResult(src.id, "*", "refused", "license or URL still VERIFY (SPEC §14, invariant 4)"))
        return results
    verified = str(src.extra.get("verified", "none"))
    if verified != "confirmed":
        print(f"fetch  note     {src.id}: license '{src.license}' has verification status '{verified}'; confirm first-hand and set verified: confirmed before publish (SPEC §15)")

    for fname in src.files:
        dest = dest_dir / fname
        key = (src.id, fname)
        if dest.exists():
            digest = sha256_of(dest)
            # a file:// source (fixtures) that was regenerated since the last run is stale even
            # when it matches the recorded checksum; the source is local, so comparing is free
            local_src = _resolve_file_url(_file_url_for(src, fname), settings.root) if src.url and src.url.startswith("file://") else None
            stale = local_src is not None and local_src.exists() and sha256_of(local_src) != digest
            if stale:
                checksums.pop(key, None)  # fall through to the copy below
            elif checksums.get(key) == digest:
                results.append(FetchResult(src.id, fname, "cached", digest[:12]))
                continue
            elif src.access in ("manual", "dataverse") or checksums.get(key) is None:
                # A file with no recorded checksum is complete (downloads land under a .part name
                # and are renamed only when finished), so record it instead of pulling multi-GB
                # rasters a second time. A recorded checksum that differs still re-downloads.
                # A hand-placed file that differs from last time is accepted (Saj put it there)
                # but said out loud, so a new vintage never slips in unnoticed.
                previous = checksums.get(key)
                checksums[key] = digest
                note = f"; REPLACES recorded {previous[:12]}: a different file than last time, check its vintage" if previous else ""
                results.append(FetchResult(src.id, fname, "ok", f"present ({src.access}), recorded {digest[:12]}{note}"))
                continue
            # else: checksum mismatch -> re-download below
        expected = checksums.get(key)
        if expected and mirror is not None and mirror.restore(expected, dest):
            results.append(FetchResult(src.id, fname, "ok", f"restored {expected[:12]} from the raw mirror"))
            continue
        if src.access == "manual":
            results.append(FetchResult(src.id, fname, "missing", f"manual source; expected at {dest}"))
            continue
        try:
            url = _file_url_for(src, fname)
            if src.access == "dataverse":
                guest = dataverse_guestbook(settings.root)
                if guest is None:
                    results.append(FetchResult(src.id, fname, "missing", f"Dataverse guestbook fields are not set in .env; download by hand to {dest}"))
                    continue
                url = dataverse_signed_url(url, guest)
            tmp = _download(url, dest, settings.root)
        except Exception as exc:  # noqa: BLE001 - report and continue with other sources
            results.append(FetchResult(src.id, fname, "error", str(exc)))
            continue
        digest = sha256_of(tmp)
        expected = checksums.get(key)
        if expected and expected != digest:
            # keep the verified file (if any) and park the new one beside it for a deliberate look
            aside = dest.with_name(dest.name + ".new")
            tmp.replace(aside)
            kept = f"kept {dest.name}, " if dest.exists() else ""
            results.append(FetchResult(src.id, fname, "error", f"checksum changed: expected {expected[:12]}, got {digest[:12]}; source vintage may have moved. {kept}new download at {aside}; to accept it, move it over {dest.name} and delete its line in CHECKSUMS"))
            continue
        tmp.replace(dest)
        checksums[key] = digest
        results.append(FetchResult(src.id, fname, "ok", digest[:12]))
    return results


def run(settings: Settings, only: list[str] | None = None) -> list[FetchResult]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    checksums_path = settings.raw_dir / "CHECKSUMS"
    checksums = read_checksums(checksums_path)
    from ..mirror import from_env

    mirror = from_env(settings)
    if mirror is not None:
        print(f"fetch  raw mirror: bucket {mirror.bucket} (recorded files come from it first)")
    results: list[FetchResult] = []
    for sid, src in sources.items():
        if only and sid not in only:
            continue
        for r in fetch_source(src, settings, checksums, mirror):
            results.append(r)
            print(f"fetch  {r.status:8s} {r.source}/{r.file}  {r.detail}")
            if r.status == "missing" and src.recipe:
                print("       recipe:\n" + "\n".join("         " + line for line in src.recipe.strip().splitlines()))
    # merge with whatever another fetch process recorded meanwhile (large sources are fetched in
    # parallel on the laptop); this run's entries win for the files it handled
    write_checksums(checksums_path, {**read_checksums(checksums_path), **checksums})
    n = {s: sum(1 for r in results if r.status == s) for s in ("ok", "cached", "missing", "refused", "error")}
    print(f"fetch  summary: {n}")
    if n["refused"] or n["error"]:
        print("fetch  some sources were refused or failed; see above", file=sys.stderr)
    return results
