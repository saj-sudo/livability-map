"""Eurostat Census 2021 1 km grid, V3 (SPEC §20.6, §15): grid cells -> WGS84 points with rates.

The download is a 566 MB zip; the loader reads its 76 MB parquet member (``member:`` on the
source). ``GRD_ID`` is ``CRS3035RES1000mN{y}E{x}``: the south-west corner of a 1 km cell in
ETRS89-LAEA (EPSG:3035), so the cell centre is corner + 500 m. Values -8888 (confidential) and
-9999 (not available) become missing, never 0 (invariant 3). Rows without a grid code
(``CC_unallocated`` population) are dropped: they have no location.

Output columns: ``lat, lng, pop, pop_1564, emp, emp_rate, share_ge65``. ``emp_rate`` is
``EMP / Y_1564`` where both are known and ``Y_1564 > 0``, clipped to 0-1 (disclosure control can
push EMP above the working-age count). The ``point_mean`` joiner weights it by ``pop_1564``.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd
from pyproj import Transformer

_ID = r"CRS3035RES1000mN(\d+)E(\d+)"
NEEDED = ["GRD_ID", "T", "Y_1564", "Y_GE65", "EMP"]
SENTINELS = (-8888, -9999)
HALF_CELL = 500.0


def parse_grd_id(ids: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Cell-centre (x, y) in EPSG:3035 metres; NaN for ids that are not grid codes."""
    parts = ids.astype(str).str.extract(_ID)
    y = parts[0].astype("float64").to_numpy() + HALF_CELL
    x = parts[1].astype("float64").to_numpy() + HALF_CELL
    return x, y


def to_wgs84(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lng, lat = Transformer.from_crs(3035, 4326, always_xy=True).transform(x, y)
    return np.asarray(lat, dtype="float64"), np.asarray(lng, dtype="float64")


def load_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Parsed grid table -> points with counts and rates."""
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        raise KeyError(f"Eurostat census grid: columns {missing} not found; the V3 layout may have changed (SPEC §15)")
    df = df[NEEDED].copy()
    for col in ("T", "Y_1564", "Y_GE65", "EMP"):
        v = pd.to_numeric(df[col], errors="coerce")
        df[col] = v.where(~v.isin(SENTINELS))
    x, y = parse_grd_id(df["GRD_ID"])
    keep = np.isfinite(x) & np.isfinite(y)
    df, x, y = df[keep].reset_index(drop=True), x[keep], y[keep]
    lat, lng = to_wgs84(x, y)
    working = df["Y_1564"].where(df["Y_1564"] > 0)
    total = df["T"].where(df["T"] > 0)
    return pd.DataFrame(
        {
            "lat": lat,
            "lng": lng,
            "pop": df["T"],
            "pop_1564": df["Y_1564"],
            "emp": df["EMP"],
            "emp_rate": (df["EMP"] / working).clip(0, 1),
            "share_ge65": (df["Y_GE65"] / total).clip(0, 1),
        }
    )


def load(settings, source, sources) -> pd.DataFrame:
    raw = settings.raw(source.id) / source.files[0]
    with zipfile.ZipFile(raw) as zf:
        data = zf.read(source.extra["member"])
    return load_frame(pd.read_parquet(io.BytesIO(data), columns=NEEDED))
