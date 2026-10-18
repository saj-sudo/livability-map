"""``validate`` stage (SPEC §5, §13.38): the gate between ``tiles`` and ``publish``.

``publish`` runs the same checks itself and refuses on any error, so a broken build cannot ship
by skipping this stage; running it alone answers "is this build safe to publish?" without
uploading anything. Each finding is ``error`` (publish refuses) or ``warn`` (printed, recorded).

Checks, for every exported resolution:
- the manifest lists every archive the resolution plan builds, each archive's bytes and sha256
  match the manifest, and each archive is fresh for the parquet and code it was built from
  (``export`` without ``tiles`` afterwards is caught here);
- inhabited hexes exist, and every hazard reaches at least one inhabited hex;
- every life dimension reaches at least one inhabited hex at the land resolutions, unless all
  its sources are missing downloads (then it is a warning naming them: the web app disables an
  empty dimension and says so, SPEC §10);
- against a baseline manifest (the build that is live), no resolution, dimension or hazard
  loses more than ``max_drop`` of its inhabited coverage and no dimension disappears.

Release builds (``release=True``, used for the r2 target) also require a real, whole-world
build: not fixtures, no ``--bbox``, every ``land`` resolution exported.

The report goes to ``data/out/validate.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .. import manifest, stage_cache, tiler
from ..attrs import HAZARD_IDS
from ..config import Settings
from ..registry import load_dimensions, load_sources

MAX_DROP = 0.05  # a release may lose at most 5% of any layer's inhabited coverage without saying so


@dataclass
class Finding:
    level: str  # error | warn
    check: str
    message: str


def covered(coverage: dict[str, int]) -> int:
    """Inhabited hexes with a value (every resolution tag except ``none``)."""
    return sum(int(v) for k, v in coverage.items() if k != "none")


def _hazard_covered(m: dict, res: str, hz: str) -> int | None:
    inhabited = m.get("coverage_summary", {}).get(res, {}).get("hexes_inhabited")
    without = m.get("known_gaps", {}).get(res, {}).get(hz, {}).get("inhabited_hexes_without_data")
    if inhabited is None or without is None:
        return None
    return int(inhabited) - int(without)


def _archives(settings: Settings, m: dict) -> list[Finding]:
    from . import tiles

    out: list[Finding] = []
    try:
        by_archive = tiles.layer_specs(settings)
    except FileNotFoundError as exc:
        return [Finding("error", "archives", str(exc))]
    listed = m.get("tiles", {})
    for name, specs in sorted(by_archive.items()):
        entry = listed.get(name)
        path = settings.out_dir / f"{name}.pmtiles"
        if entry is None or not path.is_file():
            out.append(Finding("error", "archives", f"{name}.pmtiles is not built for the exported layers ({', '.join(s.name for s in specs)}): run `tiles`"))
            continue
        if path.stat().st_size != entry.get("bytes"):
            out.append(Finding("error", "archives", f"{name}.pmtiles is {path.stat().st_size} bytes but the manifest says {entry.get('bytes')}: run `tiles`"))
            continue
        if tiler.sha256_file(path) != entry.get("sha256"):
            out.append(Finding("error", "archives", f"{name}.pmtiles does not match the sha256 in manifest.json: run `tiles`"))
            continue
        backend = stage_cache.read_meta(path).get("params", {}).get("backend", entry.get("backend", "python"))
        if not stage_cache.is_fresh(path, [s.parquet for s in specs], tiles.archive_params(name, specs, backend)):
            out.append(Finding("error", "archives", f"{name}.pmtiles is older than its parquet, plan or code (export or a code change ran after tiles): run `tiles`"))
    for name in sorted(set(listed) - set(by_archive)):
        out.append(Finding("warn", "archives", f"manifest lists {name} but no exported resolution feeds it"))
    return out


def _skipped(settings: Settings, res: str) -> set[str]:
    return set(stage_cache.read_meta(settings.stage_path("dims", int(res))).get("skipped_sources", {}))


def _contents(settings: Settings, m: dict) -> list[Finding]:
    out: list[Finding] = []
    sources = load_sources(settings.sources_path)
    registry = load_dimensions(settings.dimensions_path, sources)
    land = {str(r["res"]) for r in m.get("resolution_plan", []) if r.get("complete")}
    entries = {d["id"]: d for d in m.get("dimensions", [])}
    for dim in registry.values():
        if dim.group != "hazard" and dim.joiners and dim.id not in entries:
            out.append(Finding("error", "dimensions", f"{dim.id} is in dimensions.yaml but not in manifest.json: run `dims`, `score` and `export`"))
    for res, summary in sorted(m.get("coverage_summary", {}).items(), key=lambda kv: int(kv[0])):
        if not summary.get("hexes_inhabited"):
            out.append(Finding("error", "population", f"res {res}: no inhabited hexes (check `pop` and the GHSL raster)"))
            continue
        for hz in HAZARD_IDS:
            n = _hazard_covered(m, res, hz)
            if n is not None and n <= 0:
                out.append(Finding("error", "hazards", f"res {res}: {hz} has no value on any inhabited hex"))
        if res not in land:
            continue  # derived resolutions cover chosen places only; a country-only layer can miss them all
        skipped = _skipped(settings, res)
        for dim_id, entry in sorted(entries.items()):
            dim = registry.get(dim_id)
            if dim is None or not dim.joiners:
                continue
            if covered(entry.get("coverage", {}).get(res, {})) > 0:
                continue
            used = sorted({spec.source for spec in dim.joiners})
            missing = [s for s in used if s in skipped]
            if missing and len(missing) == len(used):
                out.append(Finding("warn", "dimensions", f"res {res}: {dim_id} has no data because its sources are not downloaded ({', '.join(missing)}); the map shows it as unavailable"))
            else:
                out.append(Finding("error", "dimensions", f"res {res}: {dim_id} reaches no inhabited hex although {', '.join(s for s in used if s not in skipped)} loaded (a changed file format turns values into NaN silently): check its prep loader"))
    return out


def _drop(before: int, after: int) -> float:
    return (before - after) / before if before else 0.0


def _against(m: dict, baseline: dict, max_drop: float) -> list[Finding]:
    out: list[Finding] = []
    label = baseline.get("built_at") or "the live build"
    for res, before in baseline.get("coverage_summary", {}).items():
        after = m.get("coverage_summary", {}).get(res)
        if after is None:
            out.append(Finding("error", "regression", f"res {res} was in {label} but is not in this build"))
            continue
        d = _drop(int(before.get("hexes_inhabited") or 0), int(after.get("hexes_inhabited") or 0))
        if d > max_drop:
            out.append(Finding("error", "regression", f"res {res}: inhabited hexes fell {100 * d:.1f}% since {label}"))
        for hz in HAZARD_IDS:
            b, a = _hazard_covered(baseline, res, hz), _hazard_covered(m, res, hz)
            if b and a is not None and _drop(b, a) > max_drop:
                out.append(Finding("error", "regression", f"res {res}: {hz} covers {100 * _drop(b, a):.1f}% fewer inhabited hexes than {label}"))
    now = {d["id"]: d for d in m.get("dimensions", [])}
    for entry in baseline.get("dimensions", []):
        cur = now.get(entry["id"])
        if cur is None:
            out.append(Finding("error", "regression", f"{entry['id']} was in {label} but is not in this build"))
            continue
        for res, cov in entry.get("coverage", {}).items():
            b, a = covered(cov), covered(cur.get("coverage", {}).get(res, {}))
            if b >= 20 and _drop(b, a) > max_drop:  # tiny layers (fixtures, one city) would be noise
                out.append(Finding("error", "regression", f"res {res}: {entry['id']} covers {100 * _drop(b, a):.1f}% fewer inhabited hexes than {label} ({b} -> {a})"))
    return out


def _release(settings: Settings, m: dict) -> list[Finding]:
    out: list[Finding] = []
    if settings.fixtures or m.get("fixtures"):
        out.append(Finding("error", "release", "this is a fixture build; only a real build can be released"))
    if settings.bbox or m.get("bbox"):
        out.append(Finding("error", "release", "this is a --bbox subregion build; only a whole-world build can be released"))
    exported = {int(r) for r in m.get("h3_res", [])}
    for row in m.get("resolution_plan", []):
        if row.get("complete") and int(row["res"]) not in exported:
            out.append(Finding("error", "release", f"res {row['res']} (fill: land) is not exported; a release needs every land resolution"))
    return out


def check(settings: Settings, baseline: dict | None = None, max_drop: float = MAX_DROP, release: bool = False) -> list[Finding]:
    """Every finding for the current build (no side effects)."""
    m = manifest.load(settings)
    findings = _archives(settings, m) + _contents(settings, m)
    if release:
        findings += _release(settings, m)
    if baseline:
        findings += _against(m, baseline, max_drop)
    return findings


def baseline_path(settings: Settings):
    """Where ``publish --target r2`` keeps a copy of the manifest it put live."""
    return settings.out_dir / "published" / "manifest.json"


def local_baseline(settings: Settings) -> dict | None:
    p = baseline_path(settings)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def report(settings: Settings, findings: list[Finding]) -> None:
    errors = [f for f in findings if f.level == "error"]
    for f in findings:
        print(f"validate {f.level:5s} {f.check}: {f.message}")
    print(f"validate {len(errors)} error(s), {len(findings) - len(errors)} warning(s)")
    stage_cache.write_atomic(settings.out_dir / "validate.json", json.dumps({"findings": [asdict(f) for f in findings]}, indent=2))
    if errors:
        raise ValueError(f"validate found {len(errors)} problem(s), the first: {errors[0].message} (all of them are listed above and in validate.json)")


def run(settings: Settings, max_drop: float = MAX_DROP, release: bool = False, baseline: dict | None = None) -> list[Finding]:
    findings = check(settings, baseline if baseline is not None else local_baseline(settings), max_drop, release)
    report(settings, findings)
    return findings
