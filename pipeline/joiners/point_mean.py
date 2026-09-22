"""``point_mean``: the (weighted) mean of point values inside each hex (resolution tag ``hex``).

Used for the Ookla speed tiles (SPEC §20.3): every ~610 m tile becomes a point at its centroid
carrying ``avg_d_kbps`` and the number of ``tests`` behind it; a hex's value is the
tests-weighted mean of the tiles whose centroid falls in it. Hexes with no point are NaN, never
0 (invariant 3), so a place Ookla does not cover shows "no data", not "no internet".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import h3util


def point_mean(hexes: pd.DataFrame, points: pd.DataFrame, res: int, field: str, weight_field: str | None = None) -> pd.Series:
    """``points`` needs ``lat``, ``lng`` and ``field`` (plus ``weight_field`` when given);
    rows with a missing coordinate, value or non-positive weight are ignored."""
    for col in ("lat", "lng", field):
        if col not in points.columns:
            raise KeyError(f"point_mean: points need a {col!r} column; got {list(points.columns)}")
    pts = points[["lat", "lng", field] + ([weight_field] if weight_field else [])].apply(pd.to_numeric, errors="coerce")
    keep = pts["lat"].between(-90, 90) & pts["lng"].between(-180, 180) & np.isfinite(pts[field])
    if weight_field:
        keep &= pts[weight_field] > 0
    pts = pts[keep]
    if pts.empty:
        return pd.Series(np.nan, index=hexes.index, name="point_mean", dtype="float64")
    cells = pd.Series(h3util.latlng_to_cells(pts["lat"].to_numpy(), pts["lng"].to_numpy(), res), index=pts.index)
    w = pts[weight_field] if weight_field else pd.Series(1.0, index=pts.index)
    num = (pts[field] * w).groupby(cells).sum()
    den = w.groupby(cells).sum()
    mean = num / den  # den > 0 by construction
    out = hexes["h3"].map(mean).astype("float64")
    out.index = hexes.index
    out.name = "point_mean"
    return out
