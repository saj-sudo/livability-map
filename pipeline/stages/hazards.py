"""``hazards`` stage (SPEC §5, §8.1, §8.2): five hazard inputs -> per-hex raw value, 0-100
percentile score and ``_ok`` flag.

Output ``data/interim/hazards_r{res}.parquet`` with, per hazard id ``heat | humid | rflood |
cflood | wstress``: the raw column (``heat_days``, ``humid_days``, ``rflood_frac``,
``cflood_frac``, ``wstress_cat``), ``{id}_score`` (nullable Int16) and ``{id}_ok`` (bool). Rules,
all from SPEC §8.1:

- heat: hd35 sampled at the hex centroid (the 0.25 degree pixel is coarser than the hex).
- humid heat: hi35 (days with heat index above 35 C) sampled the same way (SPEC §13.47).
- riverine flood: pixel-wise median depth across the five climate models, then the fraction of
  the hex's valid pixels with depth >= DEPTH_MIN (0.15 m).
- coastal flood: same fraction on the single coastal raster.
- water stress: Aqueduct 4.0 ``bau50_ws_x_c`` category (0-4) of the polygon under the centroid;
  -1 (arid / low water use) is stored but scored null with ``wstress_ok = False``.
- score: midrank percentile among inhabited hexes with data at the same resolution (§8.2).
  Missing stays missing (invariant 3).
"""

from __future__ import annotations

import time

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

from .. import h3util, rawfiles, reference, stage_cache
from ..config import Settings
from ..joiners.polygon_centroid import polygon_centroid
from ..registry import Source, load_sources
from ..scoring import percentile_score

# hazard id -> (source id, raw column name) per SPEC §6.1
HAZARDS: dict[str, tuple[str, str]] = {
    "heat": ("cckp_hd35", "heat_days"),
    "humid": ("cckp_hi35", "humid_days"),
    "rflood": ("aqueduct_floods_river", "rflood_frac"),
    "cflood": ("aqueduct_floods_coast", "cflood_frac"),
    "wstress": ("aqueduct_water_stress", "wstress_cat"),
}
WSTRESS_FIELD = "bau50_ws_x_c"
# hazards read from a CCKP 0.25 degree climatology: id -> the short variable code CCKP uses
CLIMATOLOGY = {"heat": "hd35", "humid": "hi35"}


# ---- per-hazard extractors --------------------------------------------------------------------


def _pick_variable(ds: xr.Dataset, nc_path, var: str | None, code: str) -> str:
    """The data variable to sample: ``var`` when present, else ``code`` (``hd35`` / ``hi35``),
    else the only variable with a latitude dimension. A named ``var`` that is absent falls back
    only when there is exactly one gridded variable, so a renamed file cannot pick the wrong one."""
    if var is not None and var in ds.data_vars:
        return var
    if code in ds.data_vars:
        return code
    spatial = [v for v in ds.data_vars if any(d.lower() in ("lat", "latitude") for d in ds[v].dims)]
    if var is None and spatial:
        return spatial[0]
    if var is not None and len(spatial) == 1:
        print(f"hazards: {nc_path}: no variable {var!r}; using the only gridded variable {spatial[0]!r}")
        return spatial[0]
    raise ValueError(f"{nc_path}: no data variable {var or code!r} with a latitude dimension; variables: {list(ds.data_vars)}")


def heat_days(nc_path, lat: np.ndarray, lng: np.ndarray, var: str | None = None, code: str = "hd35") -> np.ndarray:
    """Nearest-pixel sample of a CCKP days-per-year climatology (hd35 hot days, hi35 humid-heat
    days) at each centroid (NaN where the grid is masked, never 0). Handles 0..360 longitudes and
    extra non-spatial dims (time, bounds)."""
    ds = xr.open_dataset(nc_path)
    try:
        var = _pick_variable(ds, nc_path, var, code)
        da = ds[var]
        lat_name = next(d for d in da.dims if d.lower() in ("lat", "latitude"))
        lon_name = next(d for d in da.dims if d.lower() in ("lon", "longitude"))
        for d in da.dims:
            if d not in (lat_name, lon_name):
                da = da.isel({d: 0})  # climatologies carry a single time step
        lon = da[lon_name].values
        if lon.max() > 180:
            da = da.assign_coords({lon_name: ((lon + 180) % 360) - 180}).sortby(lon_name)
        sampled = da.sel(
            {
                lat_name: xr.DataArray(np.asarray(lat), dims="pts"),
                lon_name: xr.DataArray(np.asarray(lng), dims="pts"),
            },
            method="nearest",
        )
        return sampled.values.astype("float64")
    finally:
        ds.close()


def flood_fraction(paths: list, res: int, depth_min: float, bbox, cells=None) -> pd.Series:
    """Fraction of valid pixels with inundation depth >= depth_min, per hex (index h3).
    Several paths -> pixel-wise median across them first (riverine climate models). ``cells``
    limits the work to the hexes that exist at this resolution."""
    if len(paths) == 1:
        agg = h3util.aggregate_raster(paths[0], res, "frac_above", threshold=depth_min, bbox=bbox, cells=cells)
    else:
        agg = h3util.aggregate_rasters(paths, res, "frac_above", threshold=depth_min, bbox=bbox, reducer="median", cells=cells)
    return agg.set_index("h3")["value"]


def water_stress(settings: Settings, source: Source, hexes: pd.DataFrame) -> pd.Series:
    """``bau50_ws_x_c`` of the Aqueduct polygon under each centroid (NaN where none)."""
    path = rawfiles.resolve_vector(settings, source)
    layer = source.extra.get("layer")
    kwargs = {"layer": layer} if layer else {}
    polys = gpd.read_file(path, columns=[WSTRESS_FIELD], **kwargs)
    return polygon_centroid(hexes, polys, WSTRESS_FIELD)


# ---- stage -------------------------------------------------------------------------------------


def _source_files(settings: Settings, sources: dict[str, Source], sid: str) -> list:
    src = sources[sid]
    files = [settings.raw(sid) / f for f in src.files]
    missing = [str(f) for f in files if not f.exists()]
    if missing:
        raise FileNotFoundError(f"hazard source {sid} not fetched: {missing[0]} (run `fetch` first)")
    return files


def run(settings: Settings) -> dict[int, dict[str, int]]:
    settings.ensure_dirs()
    sources = load_sources(settings.sources_path)
    files = {hz: _source_files(settings, sources, sid) for hz, (sid, _) in HAZARDS.items()}
    counts: dict[int, dict[str, int]] = {}
    for res in settings.res:
        hexes_path, pop_path = settings.hexes_path(res), settings.stage_path("pop", res)
        for p in (hexes_path, pop_path):
            if not p.exists():
                raise FileNotFoundError(f"{p} missing (run `grid` and `pop` first)")
        out = settings.stage_path("hazards", res)
        inputs = [f for fs in files.values() for f in fs] + [hexes_path, pop_path] + reference.reference_inputs(settings, res, ("pop", "hazards"))
        params = {"res": res, "bbox": settings.bbox, "depth_min": settings.depth_min, "stage": "hazards", "reference_res": settings.plan.reference_res(res)}
        if stage_cache.is_fresh(out, inputs, params, settings.force):
            df = pd.read_parquet(out)
            counts[res] = {hz: int(df[f"{hz}_ok"].sum()) for hz in HAZARDS}
            print(f"hazards res {res}: up to date ({counts[res]}), skipping")
            continue
        t0 = time.time()
        # SPEC §13.32: a derived resolution is ranked against the finest complete resolution
        ref = reference.reference_frame(settings, res)
        for hz in HAZARDS:
            reference.require(ref, f"{hz}_ok", "hazards", settings, res)
        hexes = pd.read_parquet(hexes_path, columns=["h3", "lat", "lng"]).merge(
            pd.read_parquet(pop_path, columns=["h3", "inhabited"]), on="h3", how="left"
        )
        hexes["inhabited"] = hexes["inhabited"].fillna(False).astype(bool)
        df = pd.DataFrame({"h3": hexes["h3"]})

        # heat and humid heat (§8.1 bullet 1, §13.47): centroid sample of the coarse climatology
        for hz, code in CLIMATOLOGY.items():
            src = sources[HAZARDS[hz][0]]
            nc = rawfiles.resolve_raster(settings, src)
            sampled = heat_days(nc, hexes["lat"].to_numpy(), hexes["lng"].to_numpy(), src.extra.get("variable"), code)
            col = HAZARDS[hz][1]
            df[col] = sampled.astype("float32")
            df[f"{hz}_ok"] = df[col].notna()

        # floods (§8.1 bullet 2): fraction of pixels at or above DEPTH_MIN
        for hz in ("rflood", "cflood"):
            src = sources[HAZARDS[hz][0]]
            rasters = [rawfiles.resolve_raster(settings, src, i) for i in range(len(src.files))]
            frac = flood_fraction(rasters, res, settings.depth_min, settings.bbox, cells=hexes["h3"])
            col = HAZARDS[hz][1]
            df[col] = df["h3"].map(frac).astype("float32")
            df[f"{hz}_ok"] = df[col].notna()

        # water stress (§8.1 bullet 3): category at the centroid, -1 kept but not scored
        cat = water_stress(settings, sources[HAZARDS["wstress"][0]], hexes)
        df["wstress_cat"] = pd.array(np.round(pd.to_numeric(cat, errors="coerce").to_numpy()), dtype="Int16")
        df["wstress_ok"] = df["wstress_cat"].notna() & (df["wstress_cat"].fillna(-1) >= 0)

        # scores (§8.2): percentile among inhabited hexes with data (of the reference res, §13.32)
        for hz in HAZARDS:
            raw = df[HAZARDS[hz][1]].astype("float64").where(df[f"{hz}_ok"])
            ref_values = None if ref is None else ref.loc[ref[f"{hz}_ok"].fillna(False).astype(bool), HAZARDS[hz][1]].to_numpy(dtype="float64")
            df[f"{hz}_score"] = percentile_score(raw, hexes["inhabited"] & df[f"{hz}_ok"], reference=ref_values)

        cols = ["h3"]
        for hz, (_, rawcol) in HAZARDS.items():
            cols += [rawcol, f"{hz}_score", f"{hz}_ok"]
        df = df[cols]
        with stage_cache.atomic_path(out) as tmp:
            df.to_parquet(tmp, index=False)
        stage_cache.record(out, inputs, params, {"rows": len(df)})
        counts[res] = {hz: int(df[f"{hz}_ok"].sum()) for hz in HAZARDS}
        summary = ", ".join(f"{hz} {n}/{len(df)} ok" for hz, n in counts[res].items())
        print(f"hazards res {res}: {summary} in {time.time() - t0:.1f}s -> {out.name}")
        if settings.bbox:
            print("hazards note: percentile scores are relative to this bbox, not the world (SPEC §8.2)")
    return counts
