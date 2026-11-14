"""Global Energy Monitor trackers (SPEC §13.49): operating plants as points for ``industry``.

GEM publishes one spreadsheet per tracker (coal plants, gas plants, steel plants, cement and
concrete ...), downloaded through a form, CC BY 4.0. Rows are units or plants with latitude,
longitude and a status. The loader keeps operating rows with coordinates and collapses units of
one plant (same coordinates to ~100 m) into one point. It never runs on its own: the Climate TRACE
loader merges these points in when the files are present (``also_uses``), dropping a GEM plant
that lies within ``MERGE_KM`` of a Climate TRACE asset so one facility is not counted twice.

Sheet and column names are from memory (``verified: search``): the loader takes the first sheet
that has latitude and longitude columns and stops with the columns it found otherwise.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

LAT = ("latitude", "lat")
LNG = ("longitude", "lon", "lng")
STATUS = ("status", "operating status", "plant status", "unit status")
MERGE_KM = 2.0


def _find(columns, names) -> str | None:
    lower = {str(c).strip().lower(): c for c in columns}
    return next((lower[n] for n in names if n in lower), None)


def points_from_frame(df: pd.DataFrame, where: str = "table") -> pd.DataFrame:
    """Operating plants with coordinates as ``lat, lng`` (one row per plant)."""
    lat, lng = _find(df.columns, LAT), _find(df.columns, LNG)
    if lat is None or lng is None:
        raise ValueError(f"gem: {where} has no latitude/longitude columns (found {sorted(map(str, df.columns))[:30]})")
    d = pd.DataFrame({"lat": pd.to_numeric(df[lat], errors="coerce"), "lng": pd.to_numeric(df[lng], errors="coerce")})
    status = _find(df.columns, STATUS)
    if status is not None:
        d = d[df[status].astype(str).str.strip().str.lower().str.startswith("operating")]
    d = d[d["lat"].between(-90, 90) & d["lng"].between(-180, 180)]
    d = d.assign(_k=d["lat"].round(3).astype(str) + "," + d["lng"].round(3).astype(str)).drop_duplicates("_k")
    return d[["lat", "lng"]].reset_index(drop=True)


def load_workbook(path: Path) -> pd.DataFrame:
    """The plants of one tracker workbook: the first sheet with coordinate columns."""
    sheets = pd.read_excel(path, sheet_name=None)
    for name, df in sheets.items():
        if _find(df.columns, LAT) is not None and _find(df.columns, LNG) is not None:
            return points_from_frame(df, f"{path.name}:{name}")
    raise ValueError(f"gem: no sheet in {path.name} has latitude and longitude columns (sheets: {list(sheets)})")


def merge(base: pd.DataFrame, extra: pd.DataFrame, km: float = MERGE_KM) -> pd.DataFrame:
    """``base`` plus the ``extra`` points farther than ``km`` from every base point."""
    if extra.empty:
        return base
    if base.empty:
        return extra.assign(one=1.0)[["lat", "lng", "one"]]
    from scipy.spatial import cKDTree

    from ..joiners.point_radius import EARTH_KM, _unit

    tree = cKDTree(_unit(base["lat"].to_numpy(), base["lng"].to_numpy()))
    dist, _ = tree.query(_unit(extra["lat"].to_numpy(), extra["lng"].to_numpy()), k=1)
    far = dist > 2.0 * np.sin(km / (2.0 * EARTH_KM))
    new = extra[far].assign(one=1.0)[["lat", "lng", "one"]]
    return pd.concat([base, new], ignore_index=True)
