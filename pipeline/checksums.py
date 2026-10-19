"""``data/raw/CHECKSUMS`` and sha256 helpers (SPEC §11). A leaf module: ``manifest``, ``fetch``
and ``mirror`` all read checksums, and keeping this import-light keeps stage code fingerprints
(SPEC §13.38) from depending on code that cannot change their output.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def read_checksums(path: Path) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
