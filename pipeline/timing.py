"""Per-stage wall time and peak memory (SPEC §11), kept in ``data/interim/timings.json`` so the
manifest and /methodology can report what a build cost."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import time
from collections.abc import Iterator

from .config import Settings


def _peak_rss_bytes() -> int | None:
    try:
        import psutil

        info = psutil.Process().memory_info()
        return int(getattr(info, "peak_wset", 0) or info.rss)  # peak_wset exists on Windows
    except Exception:  # pragma: no cover - psutil missing or unsupported platform
        return None


def read(settings: Settings) -> dict:
    path = settings.interim_dir / "timings.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


@contextlib.contextmanager
def timed(settings: Settings, stage: str) -> Iterator[None]:
    """Record wall seconds and peak RSS for one stage run (only when the stage did real work is
    not known here, so every run is recorded; the newest overwrites)."""
    t0 = time.time()
    try:
        yield
    finally:
        seconds = time.time() - t0
        peak = _peak_rss_bytes()
        data = read(settings)
        prev = data.get(stage, {})
        data[stage] = {
            "seconds": round(seconds, 1),
            "max_seconds": round(max(seconds, float(prev.get("max_seconds") or 0)), 1),
            "peak_rss_mb": round(peak / 1e6, 1) if peak else None,
            "res": list(settings.res),
            "bbox": list(settings.bbox) if settings.bbox else None,
            "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }
        settings.interim_dir.mkdir(parents=True, exist_ok=True)
        (settings.interim_dir / "timings.json").write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        mem = f", peak RSS {peak / 1e9:.2f} GB" if peak else ""
        print(f"{stage:6s} took {seconds:.1f}s{mem}")
