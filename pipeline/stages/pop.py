"""``pop`` stage (SPEC §5, §8.5): GHSL population raster -> per-hex sum -> inhabited flag.

Output ``data/interim/pop_r{res}.parquet`` with ``h3, population, inhabited``. GHS-POP values
are persons per pixel, so a per-hex sum is the hex population. Hexes without any raster
coverage get population 0 and inhabited False (population is a count, so 0 is honest here;
this is the one place a missing value maps to 0, and it is documented on /methodology).
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .. import h3util, stage_cache
from ..config import Settings
from ..registry import load_sources

POP_SOURCE = "ghsl_pop"


def pop_path(settings: Settings):
    src = load_sources(settings.sources_path)[POP_SOURCE]
    return settings.raw(src.id) / src.files[0]


def run(settings: Settings) -> dict[int, int]:
    settings.ensure_dirs()
    raster = pop_path(settings)
    if not raster.exists():
        raise FileNotFoundError(f"population raster not fetched: {raster} (run `fetch` first)")
    counts: dict[int, int] = {}
    for res in settings.res:
        hexes_path = settings.hexes_path(res)
        if not hexes_path.exists():
            raise FileNotFoundError(f"{hexes_path} missing (run `grid` first)")
        out = settings.stage_path("pop", res)
        params = {"res": res, "bbox": settings.bbox, "pop_min": settings.pop_min, "stage": "pop"}
        if stage_cache.is_fresh(out, [raster, hexes_path], params, settings.force):
            df = pd.read_parquet(out)
            print(f"pop    res {res}: up to date ({int(df['inhabited'].sum())} inhabited), skipping")
            counts[res] = int(df["inhabited"].sum())
            continue
        t0 = time.time()
        hexes = pd.read_parquet(hexes_path, columns=["h3"])
        agg = h3util.aggregate_raster(raster, res, "sum", bbox=settings.bbox)
        df = hexes.merge(agg[["h3", "value"]], on="h3", how="left")
        df["population"] = np.nan_to_num(df["value"].to_numpy(), nan=0.0).round().astype("int64")
        df["inhabited"] = df["population"] >= settings.pop_min
        df = df[["h3", "population", "inhabited"]]
        df.to_parquet(out, index=False)
        stage_cache.record(out, [raster, hexes_path], params, {"rows": len(df)})
        n_inh = int(df["inhabited"].sum())
        print(
            f"pop    res {res}: {len(df)} hexes, {n_inh} inhabited (>= {settings.pop_min}), "
            f"total population {int(df['population'].sum()):,} in {time.time() - t0:.1f}s -> {out.name}"
        )
        counts[res] = n_inh
    return counts
