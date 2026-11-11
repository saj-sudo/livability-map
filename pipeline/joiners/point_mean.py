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

POINT_CHUNK = 1_000_000  # points converted and binned at a time (Ookla has ~6 million tiles)


def point_mean(hexes: pd.DataFrame, points: pd.DataFrame, res: int, field: str, weight_field: str | None = None) -> pd.Series:
    """``points`` needs ``lat``, ``lng`` and ``field`` (plus ``weight_field`` when given);
    rows with a missing coordinate, value or non-positive weight are ignored."""
    for col in ("lat", "lng", field):
        if col not in points.columns:
            raise KeyError(f"point_mean: points need a {col!r} column; got {list(points.columns)}")
    cols = ["lat", "lng", field] + ([weight_field] if weight_field else [])
    num = den = None
    # in chunks: the numeric copy and the list of cell ids exist for one chunk, not for every tile
    for start in range(0, len(points), POINT_CHUNK):
        pts = points.iloc[start : start + POINT_CHUNK][cols].apply(pd.to_numeric, errors="coerce")
        keep = pts["lat"].between(-90, 90) & pts["lng"].between(-180, 180) & np.isfinite(pts[field])
        if weight_field:
            keep &= pts[weight_field] > 0
        pts = pts[keep]
        if pts.empty:
            continue
        cells = pd.Series(h3util.latlng_to_cells(pts["lat"].to_numpy(), pts["lng"].to_numpy(), res), index=pts.index)
        w = pts[weight_field] if weight_field else pd.Series(1.0, index=pts.index)
        n, d = (pts[field] * w).groupby(cells).sum(), w.groupby(cells).sum()
        num = n if num is None else num.add(n, fill_value=0.0)
        den = d if den is None else den.add(d, fill_value=0.0)
    if num is None:
        return pd.Series(np.nan, index=hexes.index, name="point_mean", dtype="float64")
    mean = num / den  # den > 0 by construction
    out = hexes["h3"].map(mean).astype("float64")
    out.index = hexes.index
    out.name = "point_mean"
    return out
