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
    if agg not in AGGS:
        raise ValueError(f"agg must be one of {AGGS}")
    if agg == "frac_above" and threshold is None:
        raise ValueError("frac_above needs a threshold")
    acc = _Acc()
    with rasterio.open(path) as src:
        if src.crs is None or not src.crs.is_geographic:
            raise ValueError(f"{path}: raster must be in a geographic CRS (EPSG:4326); reproject first")
        nd = nodata if nodata is not None else src.nodata
        for window in _iter_windows(src, bbox, window_size):
            arr = src.read(band, window=window).astype("float64")
            valid = np.isfinite(arr)
            if nd is not None:
                valid &= arr != nd
            if not valid.any():
                continue
            cells, idx = _window_cells_index(src, window, res)
            if not cells:
                continue
            n = len(cells) + 1
            flat_idx = idx.ravel()
            flat_valid = valid.ravel()
            flat_arr = np.where(flat_valid, arr.ravel(), 0.0)
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


def sample_at_centroids(path: Path, cells: list[str], band: int = 1, nodata: float | None = None) -> pd.Series:
    """Point-sample a raster at cell centroids (for rasters coarser than the hex). NaN where nodata."""
    lat, lng = cell_centroids(cells)
    with rasterio.open(path) as src:
        nd = nodata if nodata is not None else src.nodata
        vals = np.array([v[0] for v in src.sample(zip(lng, lat, strict=True), indexes=band)], dtype="float64")
    if nd is not None:
        vals = np.where(vals == nd, np.nan, vals)
    return pd.Series(vals, index=pd.Index(cells, name="h3"), name="value")
