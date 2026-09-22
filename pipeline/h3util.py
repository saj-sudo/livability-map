"""H3 helpers: polygon -> cells, cell geometries, and raster -> H3 aggregation (SPEC §5, §14.11).

Raster aggregation is done by rasterizing hex ids into each raster window and grouping pixel
values with ``numpy.bincount``. This is pure rasterio + h3 and is exact for sums, means and
fraction-above-threshold. It is used instead of ``h3ronpy.raster.raster_to_dataframe``: that
function vectorizes regions of equal value and fills them with cells, which samples the raster
at cell centres rather than aggregating pixels, so it cannot produce a population sum (§15.11).

Coarse rasters (pixel wider than the hex, e.g. 0.25 degree CCKP at res 5) should use
``sample_at_centroids`` instead of ``aggregate_raster``.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from rasterio.windows import Window, from_bounds
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from .config import BBox

AGGS = ("sum", "mean", "frac_above")


# ---- cells and geometry ---------------------------------------------------------------------


def cells_for_geometry(geom: BaseGeometry, res: int) -> list[str]:
    """H3 cells whose centre lies inside ``geom`` (WGS84). Empty geometries yield []."""
    if geom.is_empty:
        return []
    if geom.geom_type == "GeometryCollection":
        out: set[str] = set()
        for g in geom.geoms:
            out.update(cells_for_geometry(g, res))
        return sorted(out)
    return list(h3.geo_to_cells(geom, res))


def cell_polygon(cell: str) -> Polygon:
    """Shapely polygon (lng, lat) for one cell."""
    return Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])


def cell_polygons(cells: Iterable[str]) -> list[Polygon]:
    return [cell_polygon(c) for c in cells]


def cell_centroids(cells: Iterable[str]) -> tuple[np.ndarray, np.ndarray]:
    """(lat, lng) arrays for cells."""
    latlng = np.array([h3.cell_to_latlng(c) for c in cells], dtype="float64").reshape(-1, 2)
    return latlng[:, 0], latlng[:, 1]


def cells_to_int(cells: Iterable[str]) -> np.ndarray:
    return np.array([h3.str_to_int(c) for c in cells], dtype="uint64")


def latlng_to_cells(lat: np.ndarray, lng: np.ndarray, res: int) -> list[str]:
    return [h3.latlng_to_cell(float(a), float(b), res) for a, b in zip(lat, lng, strict=True)]


def pad_degrees(res: int) -> float:
    """Padding (degrees) that guarantees every cell overlapping a box has its centre in the
    padded box: about two hex diameters, at the equator-worst case."""
    edge_km = h3.average_hexagon_edge_length(res, unit="km")
    return 4.5 * edge_km / 111.0


def cells_overlapping_bbox(bbox: BBox, res: int) -> list[str]:
    minlng, minlat, maxlng, maxlat = bbox
    pad = pad_degrees(res)
    padded = box(max(-180.0, minlng - pad), max(-90.0, minlat - pad), min(180.0, maxlng + pad), min(90.0, maxlat + pad))
    return cells_for_geometry(padded, res)


# ---- raster aggregation ---------------------------------------------------------------------


@dataclass
class _Acc:
    sums: dict[str, float] = field(default_factory=dict)
    n_valid: dict[str, int] = field(default_factory=dict)
    n_above: dict[str, int] = field(default_factory=dict)
    n_pixels: dict[str, int] = field(default_factory=dict)


def _iter_windows(src: rasterio.DatasetReader, bbox: BBox | None, size: int) -> Iterable[Window]:
    if bbox is None:
        full = Window(0, 0, src.width, src.height)
    else:
        full = from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
        # clip to dataset extent
        col0 = max(0, int(full.col_off))
        row0 = max(0, int(full.row_off))
        col1 = min(src.width, int(full.col_off + full.width))
        row1 = min(src.height, int(full.row_off + full.height))
        if col1 <= col0 or row1 <= row0:
            return
        full = Window(col0, row0, col1 - col0, row1 - row0)
    if not src.is_tiled:
        # Striped GeoTIFFs (one row per strip, e.g. the Aqueduct flood rasters) decode a whole
        # 43,200-pixel strip for any window touching it, so square windows would re-decode each
        # strip once per column. Read full-width strips of about size*size pixels instead.
        rows_per = max(1, (size * size) // max(1, int(full.width)))
        col, width = int(full.col_off), int(full.width)
        row_end = int(full.row_off + full.height)
        for row in range(int(full.row_off), row_end, rows_per):
            yield Window(col, row, width, min(rows_per, row_end - row))
        return
    for row in range(int(full.row_off), int(full.row_off + full.height), size):
        for col in range(int(full.col_off), int(full.col_off + full.width), size):
            h = min(size, int(full.row_off + full.height) - row)
            w = min(size, int(full.col_off + full.width) - col)
            yield Window(col, row, w, h)


def _window_cells_index(src: rasterio.DatasetReader, window: Window, res: int) -> tuple[list[str], np.ndarray]:
    """Rasterize cell polygons into the window; returns (cells, index array) where index 0 = no cell."""
    bounds = rasterio.windows.bounds(window, src.transform)
    cells = cells_overlapping_bbox(bounds, res)
    if not cells:
        return [], np.zeros((int(window.height), int(window.width)), dtype="int32")
    transform = src.window_transform(window)
    shapes = []
    for i, c in enumerate(cells, start=1):
        poly = cell_polygon(c)
        # cells straddling the antimeridian produce a bogus polygon spanning the globe; skip
        if poly.bounds[2] - poly.bounds[0] > 180:
            continue
        shapes.append((poly, i))
    idx = features.rasterize(
        shapes,
        out_shape=(int(window.height), int(window.width)),
        transform=transform,
        fill=0,
        dtype="int32",
        all_touched=False,
    )
    return cells, idx


def _mask_valid(arr: np.ndarray, nodata: float | None) -> np.ndarray:
    """Pixels that carry a value: finite and not the nodata sentinel."""
    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= arr != nodata
    return valid


def _accumulate(acc: _Acc, arr: np.ndarray, valid: np.ndarray, cells: list[str], idx: np.ndarray, agg: str, threshold: float | None) -> None:
    """Group one window's pixels by hex (np.bincount on the rasterized id image) and add the
    per-hex sums / valid counts / above-threshold counts to the running totals in ``acc``."""
    n = len(cells) + 1
    flat_idx = idx.ravel()
    flat_valid = valid.ravel()
    flat_arr = np.where(flat_valid, arr.ravel(), 0.0)  # invalid pixels contribute 0 to sums
    sums = np.bincount(flat_idx, weights=flat_arr, minlength=n)
    nvalid = np.bincount(flat_idx, weights=flat_valid.astype("float64"), minlength=n)
    npix = np.bincount(flat_idx, minlength=n)
    nabove = None
    if agg == "frac_above":
        above = flat_valid & (flat_arr >= threshold)
        nabove = np.bincount(flat_idx, weights=above.astype("float64"), minlength=n)
    for i, c in enumerate(cells, start=1):
        if npix[i] == 0:
            continue
        acc.sums[c] = acc.sums.get(c, 0.0) + float(sums[i])
        acc.n_valid[c] = acc.n_valid.get(c, 0) + int(nvalid[i])
        acc.n_pixels[c] = acc.n_pixels.get(c, 0) + int(npix[i])
        if nabove is not None:
            acc.n_above[c] = acc.n_above.get(c, 0) + int(nabove[i])


def _finish(acc: _Acc, agg: str) -> pd.DataFrame:
    """Turn the accumulated totals into the result frame. Cells with no valid pixel get NaN,
    never 0 (invariant 3)."""
    cells = sorted(acc.n_pixels)
    df = pd.DataFrame(
        {
            "h3": cells,
            "n_pixels": [acc.n_pixels[c] for c in cells],
            "n_valid": [acc.n_valid.get(c, 0) for c in cells],
        }
    )
    sums = np.array([acc.sums.get(c, 0.0) for c in cells])
    nvalid = df["n_valid"].to_numpy(dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        if agg == "sum":
            value = np.where(nvalid > 0, sums, np.nan)
        elif agg == "mean":
            value = np.where(nvalid > 0, sums / nvalid, np.nan)
        else:
            nabove = np.array([acc.n_above.get(c, 0) for c in cells], dtype="float64")
            df["n_above"] = nabove.astype("int64")
            value = np.where(nvalid > 0, nabove / nvalid, np.nan)
    df["value"] = value
    return df


def _check_agg(agg: str, threshold: float | None) -> None:
    if agg not in AGGS:
        raise ValueError(f"agg must be one of {AGGS}")
    if agg == "frac_above" and threshold is None:
        raise ValueError("frac_above needs a threshold")


def aggregate_raster(
    path: Path,
    res: int,
    agg: str,
    threshold: float | None = None,
    bbox: BBox | None = None,
    window_size: int = 2048,
    band: int = 1,
    nodata: float | None = None,
) -> pd.DataFrame:
    """Aggregate a WGS84 raster to H3 cells.

    Returns a DataFrame with columns ``h3, value, n_pixels, n_valid`` (and ``n_above`` for
    frac_above). ``value`` is the sum, mean, or fraction of valid pixels >= threshold.
    Cells with no valid pixel get value NaN (never 0), per invariant 3.
    """
    _check_agg(agg, threshold)
    acc = _Acc()
    with rasterio.open(path) as src:
        if src.crs is None or not src.crs.is_geographic:
            raise ValueError(f"{path}: raster must be in a geographic CRS (EPSG:4326); reproject first")
        nd = nodata if nodata is not None else src.nodata
        for window in _iter_windows(src, bbox, window_size):
            arr = src.read(band, window=window).astype("float64")
            valid = _mask_valid(arr, nd)
            if not valid.any():
                continue
            cells, idx = _window_cells_index(src, window, res)
            if not cells:
                continue
            _accumulate(acc, arr, valid, cells, idx, agg, threshold)
    return _finish(acc, agg)


def aggregate_rasters(
    paths: list[Path],
    res: int,
    agg: str,
    threshold: float | None = None,
    bbox: BBox | None = None,
    window_size: int = 1024,
    band: int = 1,
    nodata: float | None = None,
    reducer: str = "median",
) -> pd.DataFrame:
    """Like :func:`aggregate_raster`, but each pixel's value is the median (or mean) across
    several aligned rasters before aggregation. Used for the five Aqueduct riverine climate
    models (SPEC §8.1: "median depth across models, then fraction >= DEPTH_MIN").

    A pixel is valid when at least one raster has a finite, non-nodata value there; the
    reducer ignores the rasters that are missing at that pixel. All rasters must share the
    same shape and transform. Memory per window: len(paths) x window_size^2 x 8 bytes
    (5 x 1024^2 x 8 = 42 MB).
    """
    _check_agg(agg, threshold)
    if reducer not in ("median", "mean"):
        raise ValueError("reducer must be 'median' or 'mean'")
    if not paths:
        raise ValueError("aggregate_rasters needs at least one raster")
    acc = _Acc()
    srcs = [rasterio.open(p) for p in paths]
    try:
        first = srcs[0]
        if first.crs is None or not first.crs.is_geographic:
            raise ValueError(f"{paths[0]}: raster must be in a geographic CRS (EPSG:4326); reproject first")
        for s in srcs[1:]:
            if s.shape != first.shape or not np.allclose(tuple(s.transform)[:6], tuple(first.transform)[:6]):
                raise ValueError(f"{s.name}: rasters are not aligned with {first.name} (shape or transform differ); resample first")
        nodatas = [nodata if nodata is not None else s.nodata for s in srcs]
        for window in _iter_windows(first, bbox, window_size):
            stack = np.stack([s.read(band, window=window).astype("float64") for s in srcs])  # (k, h, w)
            valid_each = np.stack([_mask_valid(stack[k], nodatas[k]) for k in range(len(srcs))])
            valid = valid_each.any(axis=0)
            if not valid.any():
                continue
            stack = np.where(valid_each, stack, np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN slices are expected
                arr = np.nanmedian(stack, axis=0) if reducer == "median" else np.nanmean(stack, axis=0)
            cells, idx = _window_cells_index(first, window, res)
            if not cells:
                continue
            _accumulate(acc, arr, valid, cells, idx, agg, threshold)
    finally:
        for s in srcs:
            s.close()
    return _finish(acc, agg)


def sample_at_centroids(path: Path, cells: list[str], band: int = 1, nodata: float | None = None) -> pd.Series:
    """Point-sample a raster at cell centroids (for rasters coarser than the hex). NaN where nodata."""
    lat, lng = cell_centroids(cells)
    with rasterio.open(path) as src:
        nd = nodata if nodata is not None else src.nodata
        vals = np.array([v[0] for v in src.sample(zip(lng, lat, strict=True), indexes=band)], dtype="float64")
    if nd is not None:
        vals = np.where(vals == nd, np.nan, vals)
    return pd.Series(vals, index=pd.Index(cells, name="h3"), name="value")
