"""``tiles`` stage (SPEC §5, §9.1, §9.2, decision §13.18): ``data/out/hexes_r{res}.parquet`` ->
``data/out/hexes.pmtiles`` with layers ``hex4`` (zoom 2-4) and ``hex5`` (zoom 5-7).

Backends: ``python`` (``pipeline.tiler``, the default, runs anywhere) and ``tippecanoe`` (felt
fork, used only when the binary is on PATH and ``export --geojson`` ran). Zoom plan: hex4 at
z2-4 with the slim attribute set at z2 (a res-4 hex is ~2 px there and the fattest tiles must
stay small), hex5 at z5-7; MapLibre overzooms the z7 tiles to higher zooms without further
requests, so z8+ tiles are not built. When only res 4 exists (development runs) hex4 spans
z2-maxzoom. The manifest gets the archive's sha256, size and layer table.
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

MIN_ZOOM = 2
LAYER_ZOOMS = {4: (2, 4), 5: (5, 7)}  # res -> (minzoom, maxzoom) when both resolutions exist
SLIM_BELOW = {4: 3}  # hex4 ships the slim attribute set below zoom 3


def tippecanoe_path() -> str | None:
    return shutil.which("tippecanoe")


def layer_specs(settings: Settings, maxzoom: int) -> list[tiler.LayerSpec]:
    dims = load_dimensions(settings.dimensions_path, load_sources(settings.sources_path))
    full = tuple(attrs.tile_attrs(dims))
    slim = tuple(attrs.style_attrs(dims))
    present = [r for r in settings.res if (settings.out_dir / f"hexes_r{r}.parquet").exists()]
    if not present:
        raise FileNotFoundError(f"no data/out/hexes_r*.parquet for res {settings.res} (run `export` first)")
    specs = []
    for res in present:
        if len(present) == 1:
            zmin, zmax = MIN_ZOOM, maxzoom
        else:
            zmin, zmax = LAYER_ZOOMS.get(res, (MIN_ZOOM, maxzoom))
            zmax = min(zmax, maxzoom) if res == max(present) else zmax
        specs.append(
            tiler.LayerSpec(
                name=f"hex{res}",
                parquet=settings.out_dir / f"hexes_r{res}.parquet",
                minzoom=zmin,
                maxzoom=zmax,
                attrs=full,
                slim_attrs=slim,
                slim_below_zoom=SLIM_BELOW.get(res),
                description=f"H3 resolution {res} hexes (SPEC §6.1 attributes)",
            )
        )
    return specs


def build_with_tippecanoe(settings: Settings, specs: list[tiler.LayerSpec], out: Path, binary: str) -> dict:
    """Optional backend: needs the geojsonl written by `export --geojson`."""
    cmd = [binary, "-o", str(out), "--force", "--no-feature-limit", "--no-tile-size-limit", "--no-tiny-polygon-reduction", "--buffer=5"]
    for spec in specs:
        gj = spec.parquet.with_suffix(".geojsonl")
        if not gj.exists():
            raise FileNotFoundError(f"{gj} missing: run `export --geojson` before the tippecanoe backend")
        cmd += ["-L", json.dumps({"file": str(gj), "layer": spec.name, "minzoom": spec.minzoom, "maxzoom": spec.maxzoom})]
    t0 = time.time()
    subprocess.run(cmd, check=True)
    import hashlib

    return {"backend": "tippecanoe", "bytes": out.stat().st_size, "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "seconds": round(time.time() - t0, 1), "layers": [{"name": s.name, "minzoom": s.minzoom, "maxzoom": s.maxzoom} for s in specs]}


def run(settings: Settings, backend: str = "auto", maxzoom: int = 7, workers: int | None = None) -> dict:
    settings.ensure_dirs()
    specs = layer_specs(settings, maxzoom)
    out = settings.out_dir / "hexes.pmtiles"
    binary = tippecanoe_path()
    chosen = backend if backend != "auto" else ("tippecanoe" if binary else "python")
    if chosen == "tippecanoe" and not binary:
        raise RuntimeError("tippecanoe is not on PATH; use --backend python (SPEC §13.18)")
    inputs = [s.parquet for s in specs]
    params = {"stage": "tiles", "backend": chosen, "maxzoom": maxzoom, "zooms": [(s.name, s.minzoom, s.maxzoom, s.slim_below_zoom) for s in specs], "attrs": list(specs[0].attrs), "slim": list(specs[0].slim_attrs), "extent": tiler.EXTENT, "buffer": tiler.BUFFER}
    if stage_cache.is_fresh(out, inputs, params, settings.force):
        info = stage_cache.read_meta(out).get("report", {})
        print(f"tiles  up to date ({info.get('tiles', '?')} tiles, {info.get('bytes', 0) / 1e6:.1f} MB), skipping")
        return info
    if chosen == "tippecanoe":
        info = build_with_tippecanoe(settings, specs, out, binary)
    else:
        report = tiler.build_pmtiles(specs, out, workers=workers)
        info = {"backend": "python", **tiler.report_json(report)}
        tiler.write_report(settings.out_dir / "tiles_report.json", report)
        big = info["largest"]
        print(f"tiles  {info['tiles']} tiles, {info['features']} features, {info['bytes'] / 1e6:.1f} MB in {info['seconds']}s; largest z{big['z']}/{big['x']}/{big['y']} {big['bytes'] / 1e3:.0f} KB gz -> {out.name}")
        for z, (n, b) in sorted(info["per_zoom"].items(), key=lambda kv: int(kv[0])):
            print(f"       z{z}: {n} tiles, {b / 1e6:.2f} MB")
    stage_cache.record(out, inputs, params, {"report": info})
    # SPEC §6.3: the manifest carries the tile archive entry
    m = manifest.load(settings)
    m["tiles"] = {"hexes": {"key": "hexes.pmtiles", "sha256": info["sha256"], "bytes": info["bytes"], "layers": info["layers"], "backend": chosen, "minzoom": min(s.minzoom for s in specs), "maxzoom": max(s.maxzoom for s in specs)}}
    manifest.write(settings, m)
    return info
