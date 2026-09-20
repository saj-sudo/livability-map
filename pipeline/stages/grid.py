"""``grid`` stage (SPEC §5, §9.1): land polygons -> H3 cells per resolution -> hexes parquet.

Output ``data/interim/hexes_r{res}.parquet`` with columns ``h3, res, lat, lng``. Cells whose
centre is in the ocean are dropped; small islands without a cell centre on land are dropped
too (documented on /methodology as a known gap).
"""

from __future__ import annotations

import time

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from .. import h3util, stage_cache
from ..config import Settings
from ..registry import load_sources

LAND_SOURCE = "natural_earth_land"


def land_path(settings: Settings):
    src = load_sources(settings.sources_path)[LAND_SOURCE]
    return settings.raw(src.id) / src.files[0]


def build_hexes(land: gpd.GeoDataFrame, res: int) -> pd.DataFrame:
    cells: set[str] = set()
    for geom in land.geometry:
        if geom is None or geom.is_empty:
            continue
        cells.update(h3util.cells_for_geometry(geom, res))
    ordered = sorted(cells)
    lat, lng = h3util.cell_centroids(ordered)
    return pd.DataFrame({"h3": ordered, "res": res, "lat": lat, "lng": lng})


def run(settings: Settings) -> dict[int, int]:
    settings.ensure_dirs()
    path = land_path(settings)
    if not path.exists():
        raise FileNotFoundError(f"land polygons not fetched: {path} (run `fetch` first)")
    counts: dict[int, int] = {}
    land: gpd.GeoDataFrame | None = None
    for res in settings.res:
        out = settings.hexes_path(res)
        params = {"res": res, "bbox": settings.bbox, "stage": "grid"}
        if stage_cache.is_fresh(out, [path], params, settings.force):
            n = len(pd.read_parquet(out, columns=["h3"]))
            print(f"grid   res {res}: up to date ({n} hexes), skipping")
            counts[res] = n
            continue
        if land is None:
            land = gpd.read_file(path)
            if land.crs is not None and land.crs.to_epsg() != 4326:
                land = land.to_crs(4326)
            if settings.bbox:
                land = gpd.clip(land, box(*settings.bbox))
        t0 = time.time()
        df = build_hexes(land, res)
        df.to_parquet(out, index=False)
        stage_cache.record(out, [path], params, {"rows": len(df)})
        print(f"grid   res {res}: {len(df)} land hexes in {time.time() - t0:.1f}s -> {out.name}")
        counts[res] = len(df)
    return counts
