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

import numpy as np
import pandas as pd

from .. import h3util
from ..config import BBox

SAMPLES = ("mean", "centroid")


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
) -> pd.Series:
    """Per-hex mean of ``path`` (EPSG:4326). ``hexes`` needs ``h3``; the result is aligned to
    its index. ``bbox`` limits the raster windows read (a ``--bbox`` run); hexes outside the
    raster's extent or the bbox come back NaN."""
    if sample not in SAMPLES:
        raise ValueError(f"sample must be one of {SAMPLES}")
    if sample == "centroid":
        vals = h3util.sample_at_centroids(path, hexes["h3"].tolist(), band=band, nodata=nodata)
        out = pd.Series(vals.to_numpy(dtype="float64"), index=hexes.index, name="raster_mean")
        return out
    agg = h3util.aggregate_raster(path, res, "mean", bbox=bbox, band=band, nodata=nodata, decimate=decimate)
    by_cell = agg.set_index("h3")["value"] if len(agg) else pd.Series(dtype="float64")
    out = hexes["h3"].map(by_cell).astype("float64")
    out.index = hexes.index
    out.name = "raster_mean"
    # hexes the raster never touched are absent from `agg` and map to NaN already; make the
    # invariant explicit for readers of this file
    return out.where(np.isfinite(out))
