"""Idempotency helper (SPEC §11): a stage skips work when its output exists and the recorded
fingerprint of inputs and parameters matches. The fingerprint lives in ``<output>.meta.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _file_fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"path": str(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def fingerprint(inputs: list[Path], params: dict[str, Any]) -> str:
    payload = {
        "inputs": [_file_fingerprint(p) for p in inputs if p.exists()],
        "params": params,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def meta_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".meta.json")


def is_fresh(output: Path, inputs: list[Path], params: dict[str, Any], force: bool = False) -> bool:
    if force or not output.exists():
        return False
    mp = meta_path(output)
    if not mp.exists():
        return False
    try:
        recorded = json.loads(mp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return recorded.get("fingerprint") == fingerprint(inputs, params)


def record(output: Path, inputs: list[Path], params: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
    payload = {"fingerprint": fingerprint(inputs, params), "params": params}
    if extra:
        payload.update(extra)
    meta_path(output).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
