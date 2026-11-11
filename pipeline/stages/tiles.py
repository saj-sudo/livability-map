"""``tiles`` stage (SPEC §5, §9.1, §9.2, decisions §13.18, §13.32): ``data/out/hexes_r{res}.parquet``
-> one PMTiles archive per plan ``archive`` (``hexes.pmtiles`` with hex4 z2-4 and hex5 z5-7,
``hexes_nbhd.pmtiles`` with hex6 z8-9 and ``hexes_city.pmtiles`` with hex7 z10-11, where built).
A layer that keeps drawing past its last zoom must close its archive, because MapLibre overzooms
per source (``resplan`` enforces this).

Zoom ranges, archives and the slim-attribute zoom come from ``manifest["resolution_plan"]``
(written by ``export`` from ``pipeline/resolution_plan.yaml``), never from a table here, so a
new resolution is a yaml change. Each layer also records ``res``, ``complete`` (every land cell
exists at that resolution) and ``overzoom``: a layer keeps drawing beyond its last zoom unless
the next finer *present* layer is complete, so res 5 still covers the world at z8+ where no
res-6 cells were built, and the web app hides only the parents a finer layer replaced
(``ref``, §6.1).

Backends: ``python`` (``pipeline.tiler``, the default, runs anywhere) and ``tippecanoe`` (felt
fork, used only when the binary is on PATH and ``export --geojson`` ran). The manifest gets each
archive's sha256, size and layer table.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from .. import attrs, manifest, stage_cache, tiler
from ..config import Settings
from ..registry import load_dimensions, load_sources


def tippecanoe_path() -> str | None:
    return shutil.which("tippecanoe")


def layer_specs(settings: Settings) -> dict[str, list[tiler.LayerSpec]]:
    """Per archive, the layers to build, with zooms from the manifest's resolution plan."""
    m = manifest.load(settings)
    plan_rows = m.get("resolution_plan")
    if not plan_rows:
        raise FileNotFoundError("manifest.json has no resolution_plan: run `export` first")
    dims = load_dimensions(settings.dimensions_path, load_sources(settings.sources_path))
    full, slim = tuple(attrs.tile_attrs(dims)), tuple(attrs.style_attrs(dims))
    # every exported plan layer, not just this run's --res: an archive always holds all its layers
    # and overzoom depends on the finer layers that exist (a `--res 6 --res 7` run must not drop hex4/5)
    present = [r for r in plan_rows if (settings.out_dir / f"hexes_r{r['res']}.parquet").exists()]
    if not present:
        raise FileNotFoundError("no data/out/hexes_r*.parquet (run `export` first)")
    by_archive: dict[str, list[tiler.LayerSpec]] = {}
    for i, row in enumerate(present):
        finer = present[i + 1 :]
        overzoom = not finer or not finer[0]["complete"]  # keep drawing where no complete finer layer exists
        by_archive.setdefault(row["archive"], []).append(
            tiler.LayerSpec(
                name=f"hex{row['res']}",
                parquet=settings.out_dir / f"hexes_r{row['res']}.parquet",
                minzoom=int(row["zooms"][0]),
                maxzoom=int(row["zooms"][1]),
                attrs=full,
                slim_attrs=slim,
                slim_below_zoom=row.get("slim_below_zoom"),
                description=f"H3 resolution {row['res']} hexes (SPEC §6.1 attributes)",
                res=int(row["res"]),
                complete=bool(row["complete"]),
                overzoom=overzoom,
            )
        )
    return by_archive


def archive_params(name: str, specs: list[tiler.LayerSpec], backend: str) -> dict:
    """The cache parameters of one archive (``validate`` asks the same question before publish)."""
    return {
        "stage": "tiles",
        "archive": name,
        "backend": backend,
        "zooms": [(s.name, s.minzoom, s.maxzoom, s.slim_below_zoom, s.overzoom) for s in specs],
        "attrs": list(specs[0].attrs),
        "slim": list(specs[0].slim_attrs),
        "extent": tiler.EXTENT,
        "buffer": tiler.BUFFER,
    }


def build_with_tippecanoe(specs: list[tiler.LayerSpec], out: Path, binary: str) -> dict:
    """Optional backend: needs the geojsonl written by `export --geojson`."""
    cmd = [binary, "-o", str(out), "--force", "--no-feature-limit", "--no-tile-size-limit", "--no-tiny-polygon-reduction", "--buffer=5"]
    for spec in specs:
        gj = spec.parquet.with_suffix(".geojsonl")
        if not gj.exists():
            raise FileNotFoundError(f"{gj} missing: run `export --geojson` before the tippecanoe backend")
        cmd += ["-L", json.dumps({"file": str(gj), "layer": spec.name, "minzoom": spec.minzoom, "maxzoom": spec.maxzoom})]
    t0 = time.time()
    subprocess.run(cmd, check=True)
    return {"backend": "tippecanoe", "bytes": out.stat().st_size, "sha256": tiler.sha256_file(out), "seconds": round(time.time() - t0, 1), "layers": [{"name": s.name, "minzoom": s.minzoom, "maxzoom": s.maxzoom} for s in specs]}


def _layer_entries(info: dict, specs: list[tiler.LayerSpec]) -> list[dict]:
    """Manifest layer rows: the tiler's report plus the plan flags the web app reads."""
    by_name = {L["name"]: L for L in info.get("layers", [])}
    return [{**by_name.get(s.name, {"name": s.name, "minzoom": s.minzoom, "maxzoom": s.maxzoom}), "res": s.res, "complete": s.complete, "overzoom": s.overzoom} for s in specs]


def run(settings: Settings, backend: str = "auto", workers: int | None = None, archive: str | None = None) -> dict[str, dict]:
    settings.ensure_dirs()
    by_archive = layer_specs(settings)
    if archive and archive not in by_archive:
        raise ValueError(f"archive {archive!r} is not in the resolution plan (archives: {sorted(by_archive)})")
    binary = tippecanoe_path()
    chosen = backend if backend != "auto" else ("tippecanoe" if binary else "python")
    if chosen == "tippecanoe" and not binary:
        raise RuntimeError("tippecanoe is not on PATH; use --backend python (SPEC §13.18)")
    results: dict[str, dict] = {}
    m = manifest.load(settings)
    m.setdefault("tiles", {})
    for name, specs in by_archive.items():
        if archive and name != archive:
            continue
        out = settings.out_dir / f"{name}.pmtiles"
        inputs = [s.parquet for s in specs]
        params = archive_params(name, specs, chosen)
        if stage_cache.is_fresh(out, inputs, params, settings.force):
            info = stage_cache.read_meta(out).get("report", {})
            print(f"tiles  {name}: up to date ({info.get('tiles', '?')} tiles, {info.get('bytes', 0) / 1e6:.1f} MB), skipping")
        elif chosen == "tippecanoe":
            info = build_with_tippecanoe(specs, out, binary)
            stage_cache.record(out, inputs, params, {"report": info})
        else:
            report = tiler.build_pmtiles(specs, out, workers=workers)
            info = {"backend": "python", **tiler.report_json(report)}
            tiler.write_report(settings.out_dir / f"{name}_tiles_report.json", report)
            big = info["largest"]
            print(f"tiles  {name}: {info['tiles']} tiles, {info['features']} features, {info['bytes'] / 1e6:.1f} MB in {info['seconds']}s; largest z{big['z']}/{big['x']}/{big['y']} {big['bytes'] / 1e3:.0f} KB gz -> {out.name}")
            for z, (n, b) in sorted(info["per_zoom"].items(), key=lambda kv: int(kv[0])):
                print(f"       z{z}: {n} tiles, {b / 1e6:.2f} MB")
            stage_cache.record(out, inputs, params, {"report": info})
        # SPEC §6.3: the manifest carries one entry per archive
        m["tiles"][name] = {
            "key": f"{name}.pmtiles",
            "sha256": info["sha256"],
            "bytes": info["bytes"],
            "layers": _layer_entries(info, specs),
            "backend": chosen,
            "minzoom": min(s.minzoom for s in specs),
            "maxzoom": max(s.maxzoom for s in specs),
        }
        results[name] = info
    manifest.write(settings, m)
    return results
