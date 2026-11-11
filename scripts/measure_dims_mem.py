"""Peak memory of the ``dims`` stage, for comparing a change against the base commit.

Runs ``python -m pipeline [--fixtures] [--res R ...] --force dims`` in its own child process and
prints that child's peak resident set (``wait4`` reports one child, so earlier stages do not
count). On the fixture world this only shows direction, because that world is 4 x 4 degrees; the
real figure is the one ``timing`` writes to ``data/interim/timings.json`` after
``python -m pipeline --res 6 dims`` on the laptop (SPEC §13.44 compares it with the 7.9 GB
recorded before the change).

    uv run python scripts/measure_dims_mem.py                  # fixture world, res 4 and 5
    uv run python scripts/measure_dims_mem.py --real --res 6   # real data (earlier stages must have run)

With the fixture world the script first runs the stages ``dims`` needs for the same resolutions.
Linux and macOS only (``os.wait4``); on Windows read ``timings.json`` instead.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

PREREQUISITES = ["fetch", "urban", "grid", "pop", "admin", "hazards"]


def pipeline_cmd(fixtures: bool, res: list[int], stage: str, force: bool = False) -> list[str]:
    """``python -m pipeline`` with its global options (they go before the stage name)."""
    cmd = [sys.executable, "-m", "pipeline"]
    if fixtures:
        cmd.append("--fixtures")
    for r in res:
        cmd += ["--res", str(r)]
    if force:
        cmd.append("--force")
    return [*cmd, stage]


def run_measured(cmd: list[str]) -> tuple[int, float]:
    """Run ``cmd`` and return (exit code, that child's peak RSS in MB)."""
    proc = subprocess.Popen(cmd)
    _, status, usage = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)
    kb_or_bytes = usage.ru_maxrss  # kilobytes on Linux, bytes on macOS
    return proc.returncode, kb_or_bytes / (1e6 if sys.platform == "darwin" else 1e3)


def main() -> int:
    ap = argparse.ArgumentParser(description="Peak RSS of the dims stage in a child process.")
    ap.add_argument("--real", action="store_true", help="use data/ instead of the fixture world")
    ap.add_argument("--res", type=int, action="append", help="resolution (repeatable); default 4 and 5")
    args = ap.parse_args()
    fixtures, res = not args.real, args.res or [4, 5]
    if fixtures:
        for stage in PREREQUISITES:
            code, _ = run_measured(pipeline_cmd(fixtures, res, stage))
            # the fixture registry holds two deliberately unfetchable examples, so fetch exits 1
            if code and stage != "fetch":
                print(f"measure: prerequisite stage {stage} failed (exit {code})", file=sys.stderr)
                return code
    t0 = time.time()
    code, peak_mb = run_measured(pipeline_cmd(fixtures, res, "dims", force=True))
    print(f"measure: dims exit {code}, {time.time() - t0:.1f}s, peak RSS {peak_mb:.0f} MB (res {res}, {'fixtures' if fixtures else 'real data'})")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
