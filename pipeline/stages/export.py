"""``export`` stage (SPEC §5, §6): the final per-hex table and the manifest.

Writes ``data/out/hexes_r{res}.parquet`` (every column from every interim stage, typed) and
``data/out/manifest.json`` (SPEC §6.3). With ``geojson=True`` it also writes
``data/out/hexes_r{res}.geojsonl`` (newline-delimited features carrying only the tile
attributes) for the optional tippecanoe backend of the ``tiles`` stage.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from .. import attrs, h3util, manifest, sanity, stage_cache
from ..config import Settings
from ..registry import load_dimensions, load_sources

INTERIM_STAGES = ("pop", "admin", "hazards", "dims", "score")


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    """Stable dtypes for the export: scores Int16, flags bool, tags str, raw floats float32."""
    out = df.copy()
    for col in out.columns:
        if col.endswith("_score") or col in ("exposure",):
            out[col] = pd.array(pd.to_numeric(out[col], errors="coerce").to_numpy(dtype="float64"), dtype="Int16")
        elif col.endswith("_ok") or col == "inhabited":
            out[col] = out[col].fillna(False).astype(bool)
        elif col.endswith("_res") or col in ("wb_source", "scenario", "horizon"):
            out[col] = out[col].fillna("none").astype(str)
    return out


def _feature(row: dict, keep: list[str]) -> dict:
    props = {}
    for k in keep:
        v = row.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
            continue
        if hasattr(v, "item"):
            v = v.item()
        v = attrs.round_value(k, v)
        if v is not None:
            props[k] = v
    return {"type": "Feature", "geometry": h3util.cell_polygon(row["h3"]).__geo_interface__, "properties": props}


def write_geojsonl(df: pd.DataFrame, keep: list[str], path) -> int:
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for row in df.to_dict("records"):
            fh.write(json.dumps(_feature(row, keep), separators=(",", ":")) + "\n")
            n += 1
    return n


def run(settings: Settings, geojson: bool = False) -> dict[int, int]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    dims = load_dimensions(settings.dimensions_path, sources)
    keep = attrs.tile_attrs(dims)
    counts: dict[int, int] = {}
    for res in settings.res:
        inputs = [settings.hexes_path(res)] + [settings.stage_path(s, res) for s in INTERIM_STAGES]
        for p in inputs:
            if not p.exists():
                raise FileNotFoundError(f"{p} missing: run every stage up to `score` before `export`")
        out = settings.out_dir / f"hexes_r{res}.parquet"
        params = {"res": res, "bbox": settings.bbox, "stage": "export", "geojson": geojson}
        if stage_cache.is_fresh(out, inputs, params, settings.force):
            counts[res] = int(stage_cache.read_meta(out).get("rows", 0))
            print(f"export res {res}: up to date ({counts[res]} hexes), skipping")
            continue
        t0 = time.time()
        df = _typed(sanity.load_merged(settings, res))
        missing = [c for c in keep if c not in df.columns]
        if missing:
            raise RuntimeError(f"export res {res}: tile attributes missing from the interim stages: {missing}")
        df.to_parquet(out, index=False)
        extra = {"rows": len(df)}
        if geojson:
            gj = settings.out_dir / f"hexes_r{res}.geojsonl"
            extra["geojsonl_features"] = write_geojsonl(df, keep, gj)
            print(f"export res {res}: {extra['geojsonl_features']} features -> {gj.name}")
        stage_cache.record(out, inputs, params, extra)
        counts[res] = len(df)
        print(f"export res {res}: {len(df)} hexes, {len(df.columns)} columns ({len(keep)} ship in tiles) in {time.time() - t0:.1f}s -> {out.name}")
    m = manifest.build(settings)
    path = manifest.write(settings, m)
    print(f"export manifest: {len(m['sources'])} sources, {len(m['dimensions'])} dimensions -> {path.name}")
    return counts
