"""``grid`` stage (SPEC §5, §9.1, §13.32): the resolution plan -> one hexes parquet per resolution.

``land`` entries of ``pipeline/resolution_plan.yaml``: H3 cells whose centre is on Natural Earth
land (as before); cells whose centre is in the ocean are dropped, and small islands without a
cell centre on land are absent (documented on /methodology as a known gap).

``children`` entries: the H3 children of every parent cell that matches a plan rule, keeping only
children whose centre is on land:

- ``countries``: the parent centroid's country (geoBoundaries ADM0, ISO2) is in the list;
- ``urban``: the parent polygon touches an urban ``centre`` or ``cluster`` polygon written by the
  ``urban`` stage.

Output ``data/interim/hexes_r{res}.parquet`` with ``h3, res, lat, lng`` plus, for derived
resolutions, ``parent`` (the refined cell) and ``uc_id`` (the urban polygon of the rule's kind
under the child's centroid; missing outside one). The children of a set of parents tile the
parents' union, so the coarse layer can hide a refined parent (``ref``, written by ``export``)
where the finer layer takes over.
"""

from __future__ import annotations

import time

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box

from .. import h3util, stage_cache
from ..config import Settings
from ..joiners.polygon_centroid import polygon_centroid
from ..prep.util import iso3_to_iso2
from ..registry import load_sources
from ..resplan import ResEntry

LAND_SOURCE = "natural_earth_land"
ADM0_SOURCE = "geoboundaries_adm0"


def land_path(settings: Settings):
    src = load_sources(settings.sources_path)[LAND_SOURCE]
    return settings.raw(src.id) / src.files[0]


def build_hexes(land: gpd.GeoDataFrame, res: int) -> pd.DataFrame:
    """Every cell of ``res`` whose centre is on land (a complete resolution)."""
    cells: set[str] = set()
    for geom in land.geometry:
        if geom is None or geom.is_empty:
            continue
        cells.update(h3util.cells_for_geometry(geom, res))
    ordered = sorted(cells)
    lat, lng = h3util.cell_centroids(ordered)
    return pd.DataFrame({"h3": ordered, "res": res, "lat": lat, "lng": lng})


def _on_land(land: gpd.GeoDataFrame, lng: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Which points fall inside a land polygon (STRtree, so a few million points are cheap)."""
    tree = shapely.STRtree(land.geometry.values)
    pts = shapely.points(lng, lat)
    hit = np.zeros(len(pts), dtype=bool)
    hit[tree.query(pts, predicate="within")[0]] = True
    return hit


def refine(
    parents: pd.DataFrame,
    entry: ResEntry,
    land: gpd.GeoDataFrame,
    urban: gpd.GeoDataFrame | None,
    adm0: gpd.GeoDataFrame | None,
    iso_overrides: dict[str, str],
) -> pd.DataFrame:
    """Children of the parents that match ``entry.where`` (any rule suffices), on land only."""
    match = np.zeros(len(parents), dtype=bool)
    countries = entry.where.get("countries")
    if countries:
        iso2 = iso3_to_iso2(polygon_centroid(parents, adm0, field="shapeGroup"), iso_overrides)
        match |= iso2.isin(countries).to_numpy()
    kind = entry.where.get("urban")
    urban_kind = None
    if kind:
        urban_kind = urban[urban["kind"] == kind][["uc_id", "geometry"]].reset_index(drop=True)
        polys = gpd.GeoDataFrame({"i": np.arange(len(parents))}, geometry=h3util.cell_polygons(parents["h3"]), crs=4326)
        hit = gpd.sjoin(polys, urban_kind[["geometry"]], predicate="intersects", how="inner")
        match[hit["i"].unique()] = True
    kids: list[str] = []
    parent_of: list[str] = []
    for p in parents.loc[match, "h3"]:
        c = h3.cell_to_children(p, entry.res)
        kids += c
        parent_of += [p] * len(c)
    lat, lng = h3util.cell_centroids(kids)
    df = pd.DataFrame({"h3": kids, "res": entry.res, "lat": lat, "lng": lng, "parent": parent_of})
    if len(df):
        df = df[_on_land(land, df["lng"].to_numpy(), df["lat"].to_numpy())].reset_index(drop=True)
    df["uc_id"] = pd.array([pd.NA] * len(df), dtype="Int64")
    if urban_kind is not None and len(df):
        pts = gpd.GeoDataFrame({"i": np.arange(len(df))}, geometry=gpd.points_from_xy(df["lng"], df["lat"]), crs=4326)
        within = gpd.sjoin(pts, urban_kind, predicate="within", how="inner").drop_duplicates("i")
        df.loc[within["i"].to_numpy(), "uc_id"] = within["uc_id"].to_numpy()
    return df.sort_values("h3").reset_index(drop=True)


def run(settings: Settings) -> dict[int, int]:
    settings.ensure_dirs()
    path = land_path(settings)
    if not path.exists():
        raise FileNotFoundError(f"land polygons not fetched: {path} (run `fetch` first)")
    sources = load_sources(settings.sources_path)
    adm0_path = settings.raw(ADM0_SOURCE) / sources[ADM0_SOURCE].files[0]
    counts: dict[int, int] = {}
    land: gpd.GeoDataFrame | None = None
    adm0: gpd.GeoDataFrame | None = None
    urban: gpd.GeoDataFrame | None = None

    def _land() -> gpd.GeoDataFrame:
        nonlocal land
        if land is None:
            land = gpd.read_file(path)
            if land.crs is not None and land.crs.to_epsg() != 4326:
                land = land.to_crs(4326)
            if settings.bbox:
                land = gpd.clip(land, box(*settings.bbox))
        return land

    for res in settings.res:
        entry = settings.plan.entry(res)
        out = settings.hexes_path(res)
        inputs = [path]
        if not entry.complete:
            parent_path = settings.hexes_path(entry.parent)
            if not parent_path.exists():
                raise FileNotFoundError(f"{parent_path} missing: run grid for res {entry.parent} first (res {res} is built from its cells)")
            inputs.append(parent_path)
            if "urban" in entry.where:
                if not settings.urban_path.exists():
                    raise FileNotFoundError(f"{settings.urban_path} missing: run `urban` first (res {res} refines urban {entry.where['urban']}s)")
                inputs.append(settings.urban_path)
            if "countries" in entry.where:
                if not adm0_path.exists():
                    raise FileNotFoundError(f"boundaries not fetched: {adm0_path} (run `fetch` first)")
                inputs.append(adm0_path)
        params = {"res": res, "bbox": settings.bbox, "stage": "grid", "plan": entry.to_manifest(), "iso_overrides": settings.iso_overrides}
        if stage_cache.is_fresh(out, inputs, params, settings.force):
            n = len(pd.read_parquet(out, columns=["h3"]))
            print(f"grid   res {res}: up to date ({n} hexes), skipping")
            counts[res] = n
            continue
        t0 = time.time()
        if entry.complete:
            df = build_hexes(_land(), res)
        else:
            parents = pd.read_parquet(settings.hexes_path(entry.parent), columns=["h3", "lat", "lng"])
            if "urban" in entry.where and urban is None:
                urban = gpd.read_parquet(settings.urban_path)
            if "countries" in entry.where and adm0 is None:
                adm0 = gpd.read_file(adm0_path).to_crs(4326)
            df = refine(parents, entry, _land(), urban, adm0, settings.iso_overrides)
        df.to_parquet(out, index=False)
        stage_cache.record(out, inputs, params, {"rows": len(df)})
        how = "land hexes" if entry.complete else f"children of res {entry.parent} cells matching {entry.where}"
        print(f"grid   res {res}: {len(df)} {how} in {time.time() - t0:.1f}s -> {out.name}")
        counts[res] = len(df)
    return counts
