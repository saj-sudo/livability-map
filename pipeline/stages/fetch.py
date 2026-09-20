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
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ..config import Settings
from ..registry import Source, load_sources

CHUNK = 1 << 20
LFS_MAGIC = b"version https://git-lfs.github.com/spec/v1"


@dataclass
class FetchResult:
    source: str
    file: str
    status: str  # ok | cached | missing | refused | error
    detail: str = ""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    if path.stat().st_size > 1024:
        return False
    with open(path, "rb") as fh:
        return fh.read(len(LFS_MAGIC)) == LFS_MAGIC


def read_checksums(path: Path) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            continue
        digest, sid, fname = parts
        out[(sid, fname)] = digest
    return out


def write_checksums(path: Path, entries: dict[tuple[str, str], str]) -> None:
    lines = ["# sha256  source_id  filename   (written by `python -m pipeline fetch`, SPEC §11)"]
    for (sid, fname), digest in sorted(entries.items()):
        lines.append(f"{digest}  {sid}  {fname}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _resolve_file_url(url: str, root: Path) -> Path:
    parsed = urlparse(url)
    raw = parsed.netloc + parsed.path if parsed.netloc else parsed.path
    p = Path(raw)
    if not p.is_absolute():
        p = root / raw.lstrip("/") if raw.startswith("/") and not (root / raw).exists() else root / raw
    return p


def _download(url: str, dest: Path, root: Path) -> None:
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
    if is_lfs_pointer(tmp):
        tmp.unlink()
        raise RuntimeError("downloaded a Git LFS pointer instead of the file; use a /raw/ URL that redirects to media.githubusercontent.com")
    tmp.replace(dest)


def _file_url_for(src: Source, fname: str) -> str:
    """Per-file URL: ``url`` may point at a directory (ends with '/') or a single file."""
    assert src.url
    if src.url.endswith("/"):
        return src.url + fname
    return src.url


def fetch_source(src: Source, settings: Settings, checksums: dict[tuple[str, str], str]) -> list[FetchResult]:
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
            if checksums.get(key) == digest:
                results.append(FetchResult(src.id, fname, "cached", digest[:12]))
                continue
            if src.access == "manual":
                checksums[key] = digest
                results.append(FetchResult(src.id, fname, "ok", f"present (manual), recorded {digest[:12]}"))
                continue
            # checksum mismatch or unknown: re-download below
        if src.access == "manual":
            results.append(FetchResult(src.id, fname, "missing", f"manual source; expected at {dest}"))
            continue
        try:
            _download(_file_url_for(src, fname), dest, settings.root)
        except Exception as exc:  # noqa: BLE001 - report and continue with other sources
            results.append(FetchResult(src.id, fname, "error", str(exc)))
            continue
        digest = sha256_of(dest)
        expected = checksums.get(key)
        if expected and expected != digest:
            results.append(FetchResult(src.id, fname, "error", f"checksum changed: expected {expected[:12]}, got {digest[:12]}; source vintage may have moved (update CHECKSUMS deliberately)"))
            continue
        checksums[key] = digest
        results.append(FetchResult(src.id, fname, "ok", digest[:12]))
    return results


def run(settings: Settings, only: list[str] | None = None) -> list[FetchResult]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    checksums_path = settings.raw_dir / "CHECKSUMS"
    checksums = read_checksums(checksums_path)
    results: list[FetchResult] = []
    for sid, src in sources.items():
        if only and sid not in only:
            continue
        for r in fetch_source(src, settings, checksums):
            results.append(r)
            print(f"fetch  {r.status:8s} {r.source}/{r.file}  {r.detail}")
            if r.status == "missing" and src.recipe:
                print("       recipe:\n" + "\n".join("         " + line for line in src.recipe.strip().splitlines()))
    write_checksums(checksums_path, checksums)
    n = {s: sum(1 for r in results if r.status == s) for s in ("ok", "cached", "missing", "refused", "error")}
    print(f"fetch  summary: {n}")
    if n["refused"] or n["error"]:
        print("fetch  some sources were refused or failed; see above", file=sys.stderr)
    return results
