"""``raster_mean``: the mean of a raster's valid pixels inside each hex (resolution tag ``hex``).

Used for the hex-level layers that are finer than the hex (SPEC §20.3): travel time to
healthcare (1 km), PM2.5 (0.01 degree) and tree cover (100 m, block-averaged to 1 km first with
``decimate``). Rasters coarser than the hex (the 0.25 degree burned-area grid) cannot be
aggregated this way because a small hex may contain no pixel centre; ``sample="centroid"``
point-samples them at the hex centroid instead, the same rule the ``hazards`` stage applies to
the 0.25 degree CCKP heat climatology.

Missing (no valid pixel, nodata at the centroid, hex outside the raster) is NaN, never 0.
"""

from __future__ import annotations

from pathlib import Path

import h3
import numpy as np
import pandas as pd
import rasterio

from .. import h3util
from ..config import BBox

SAMPLES = ("mean", "centroid")
PIXELS_ACROSS = 4  # keep at least this many block-averaged pixels across a hex


def effective_decimate(decimate: int, res: int, pixel_deg: float) -> int:
    """Cap the block-averaging factor so a hex still spans ~PIXELS_ACROSS coarse pixels: a
    res-7 hex (edge 1.2 km) over 100 m pixels averages 2x2 blocks, res 6 gets 7x7 and res 5
    keeps the registry's 10x10 (SPEC §9.1: the same registry entry serves every resolution)."""
    if decimate <= 1:
        return 1
    edge_deg = h3.average_hexagon_edge_length(res, unit="km") / 111.0
    return int(max(1, min(decimate, edge_deg / (pixel_deg * PIXELS_ACROSS))))


def raster_mean(
    hexes: pd.DataFrame,
    path: Path,
    res: int,
    *,
    band: int = 1,
    nodata: float | None = None,
    decimate: int = 1,
    sample: str = "mean",
    bbox: BBox | None = None,
    cells=None,
) -> pd.Series:
    """Per-hex mean of ``path`` (EPSG:4326). ``hexes`` needs ``h3``; the result is aligned to
    its index. ``bbox`` limits the raster windows read (a ``--bbox`` run); hexes outside the
    raster's extent or the bbox come back NaN. Only the hexes given (``cells`` or ``hexes.h3``)
    are rasterized, so a derived resolution costs what its cells cost, not a world fill."""
    if sample not in SAMPLES:
        raise ValueError(f"sample must be one of {SAMPLES}")
    if sample == "centroid":
        vals = h3util.sample_at_centroids(path, hexes["h3"].tolist(), band=band, nodata=nodata)
        out = pd.Series(vals.to_numpy(dtype="float64"), index=hexes.index, name="raster_mean")
        return out
    with rasterio.open(path) as src:
        pixel_deg = abs(src.transform.a)
    d = effective_decimate(decimate, res, pixel_deg)
    agg = h3util.aggregate_raster(path, res, "mean", bbox=bbox, band=band, nodata=nodata, decimate=d, cells=cells if cells is not None else hexes["h3"])
    by_cell = agg.set_index("h3")["value"] if len(agg) else pd.Series(dtype="float64")
    out = hexes["h3"].map(by_cell).astype("float64")
    out.index = hexes.index
    out.name = "raster_mean"
    # hexes the raster never touched are absent from `agg` and map to NaN already; make the
    # invariant explicit for readers of this file
    return out.where(np.isfinite(out))
