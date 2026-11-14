"""``point_radius``: point values within a radius of each hex centre (resolution tag ``hex``).

Two uses, after Session 8 (SPEC §13.36):

- ``agg="sum"``: e.g. conflict fatalities per year within 25 km (UCDP GED). A hex with no event
  in range gets a real 0, because the event set covers the whole world: "no recorded event
  nearby" is a measurement, not missing data. That only holds while the point set is real: an
  empty point set gives NaN everywhere, and points whose value column is all non-numeric raise
  (a prep change must never turn into a world of zeros, §13.45).
- ``agg="mean"`` (optionally weighted): e.g. Meta's Relative Wealth Index, whose ~2.4 km tiles are
  sparser than a res-7 hex; averaging the tiles within a few km of the centre gives every hex a
  value where tiles exist nearby. A hex with no point in range is missing (NaN), never 0.

``per_km2=True`` (with ``agg="sum"``) divides each sum by the area searched, pi * r^2 with the
effective radius below, so a density compares fairly across resolutions whose radius differs
(everyday amenities, §13.49).

The search radius is never smaller than the hex's average edge length (about its circumradius),
so a coarse hex averages what lies inside it rather than a small disc at its centre. Distances are
exact on the sphere: points and centres become unit vectors and a KD-tree answers chord-length
queries.
"""

from __future__ import annotations

import h3
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

EARTH_KM = 6371.0088
AGGS = ("sum", "mean")
HEX_CHUNK = 50_000  # hexes queried at a time: the neighbour lists of a res-7 world are huge


def _unit(lat: np.ndarray, lng: np.ndarray) -> np.ndarray:
    la, lo = np.radians(lat), np.radians(lng)
    return np.column_stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def effective_radius_km(radius_km: float, res: int) -> float:
    """The radius actually searched: never below the hex's average edge length."""
    return max(float(radius_km), h3.average_hexagon_edge_length(res, unit="km"))


def point_radius(hexes: pd.DataFrame, points: pd.DataFrame, res: int, field: str, *, radius_km: float, agg: str = "mean", weight_field: str | None = None, per_km2: bool = False) -> pd.Series:
    if agg not in AGGS:
        raise ValueError(f"point_radius: agg must be one of {AGGS}")
    if per_km2 and agg != "sum":
        raise ValueError("point_radius: per_km2 needs agg=sum")
    for col in ("lat", "lng", field):
        if col not in points.columns:
            raise KeyError(f"point_radius: points need a {col!r} column; got {list(points.columns)}")
    cols = ["lat", "lng", field] + ([weight_field] if weight_field else [])
    pts = points[cols].apply(pd.to_numeric, errors="coerce")
    keep = pts["lat"].between(-90, 90) & pts["lng"].between(-180, 180) & np.isfinite(pts[field])
    if weight_field:
        keep &= pts[weight_field] > 0
    if len(pts) and not keep.any():
        raise ValueError(f"point_radius: none of the {len(pts)} points has a usable {field!r} value (check the prep loader)")
    pts = pts[keep]
    out = np.full(len(hexes), 0.0 if agg == "sum" and not pts.empty else np.nan)
    if not pts.empty:
        radius = effective_radius_km(radius_km, res)
        chord = 2.0 * np.sin(radius / (2.0 * EARTH_KM))
        tree = cKDTree(_unit(pts["lat"].to_numpy(), pts["lng"].to_numpy()))
        centres = _unit(hexes["lat"].to_numpy(dtype="float64"), hexes["lng"].to_numpy(dtype="float64"))
        values = pts[field].to_numpy(dtype="float64")
        weights = pts[weight_field].to_numpy(dtype="float64") if weight_field else np.ones(len(pts))
        for start in range(0, len(centres), HEX_CHUNK):
            for i, idx in enumerate(tree.query_ball_point(centres[start : start + HEX_CHUNK], chord), start=start):
                if not idx:
                    continue
                if agg == "sum":
                    out[i] = float(values[idx].sum())
                else:
                    w = weights[idx]
                    out[i] = float((values[idx] * w).sum() / w.sum())
    if per_km2:
        out = out / (np.pi * effective_radius_km(radius_km, res) ** 2)
    return pd.Series(out, index=hexes.index, name="point_radius", dtype="float64")
