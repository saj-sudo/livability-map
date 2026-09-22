"""``admin`` stage (SPEC §5, §6.1): hex centroid -> geoBoundaries admin0 / admin1.

Output ``data/interim/admin_r{res}.parquet`` with ``h3, iso_a3, iso_a2, admin1_id, admin1_name``.
Uses the ``polygon_centroid`` joiner so the same code path serves wellbeing and life dimensions.
ISO3 -> ISO2 goes through pycountry with ``Settings.iso_overrides`` for user-assigned codes.
"""

from __future__ import annotations

import time

import geopandas as gpd
import pandas as pd

from .. import stage_cache
from ..config import Settings
from ..joiners.polygon_centroid import polygon_centroid
from ..prep.util import iso3_to_iso2 as _iso3_to_iso2
from ..registry import load_sources

ADM0_SOURCE = "geoboundaries_adm0"
ADM1_SOURCE = "geoboundaries_adm1"


def iso3_to_iso2(codes: pd.Series, overrides: dict[str, str]) -> pd.Series:
    """ISO3 -> ISO2 (shared with the prep loaders; see pipeline.prep.util)."""
    return _iso3_to_iso2(codes, overrides)


def run(settings: Settings) -> dict[int, int]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    adm0_path = settings.raw(ADM0_SOURCE) / sources[ADM0_SOURCE].files[0]
    adm1_path = settings.raw(ADM1_SOURCE) / sources[ADM1_SOURCE].files[0]
    for p in (adm0_path, adm1_path):
        if not p.exists():
            raise FileNotFoundError(f"boundaries not fetched: {p} (run `fetch` first)")
    counts: dict[int, int] = {}
    adm0 = adm1 = None
    for res in settings.res:
        hexes_path = settings.hexes_path(res)
        if not hexes_path.exists():
            raise FileNotFoundError(f"{hexes_path} missing (run `grid` first)")
        out = settings.stage_path("admin", res)
        params = {"res": res, "bbox": settings.bbox, "stage": "admin", "iso_overrides": settings.iso_overrides}
        if stage_cache.is_fresh(out, [adm0_path, adm1_path, hexes_path], params, settings.force):
            df = pd.read_parquet(out)
            print(f"admin  res {res}: up to date ({df['iso_a2'].notna().sum()} with country), skipping")
            counts[res] = int(df["iso_a2"].notna().sum())
            continue
        if adm0 is None:
            adm0 = gpd.read_file(adm0_path).to_crs(4326)
            adm1 = gpd.read_file(adm1_path).to_crs(4326)
        t0 = time.time()
        hexes = pd.read_parquet(hexes_path, columns=["h3", "lat", "lng"])
        iso3 = polygon_centroid(hexes, adm0, field="shapeGroup")
        a1_id = polygon_centroid(hexes, adm1, field="shapeID")
        a1_name = polygon_centroid(hexes, adm1, field="shapeName")
        df = pd.DataFrame(
            {
                "h3": hexes["h3"],
                "iso_a3": iso3.to_numpy(),
                "iso_a2": iso3_to_iso2(iso3, settings.iso_overrides).to_numpy(),
                "admin1_id": a1_id.to_numpy(),
                "admin1_name": a1_name.to_numpy(),
            }
        )
        df.to_parquet(out, index=False)
        stage_cache.record(out, [adm0_path, adm1_path, hexes_path], params, {"rows": len(df)})
        n = int(df["iso_a2"].notna().sum())
        print(
            f"admin  res {res}: {n}/{len(df)} hexes with a country, {int(df['admin1_id'].notna().sum())} with admin1 "
            f"in {time.time() - t0:.1f}s -> {out.name}"
        )
        counts[res] = n
    return counts
