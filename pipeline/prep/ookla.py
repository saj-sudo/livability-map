"""Ookla Open Data speed tiles -> points for ``point_mean`` (SPEC §20.6 `net`).

Each parquet row is a ~610 m web-mercator z16 tile with the average download speed
(``avg_d_kbps``) of the Speedtest results run inside it and how many ``tests`` that average
rests on; ``tile_x`` / ``tile_y`` are the tile centroid in EPSG:4326. Only the four columns
needed are read (the file is 350 MB; the WKT ``tile`` column is most of it).

Output columns: ``lat, lng, d_mbps, tests`` (fixtures ship a CSV with the same four).
"""

from __future__ import annotations

import pandas as pd
import pyarrow.parquet as pq

from ..config import Settings
from ..registry import Source

COLUMNS = ["tile_x", "tile_y", "avg_d_kbps", "tests"]


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Pure: rename to the joiner's columns, kbps -> Mbps, drop tiles without a usable value."""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Ookla tiles: expected columns {COLUMNS}, missing {missing} (got {list(df.columns)})")
    out = pd.DataFrame(
        {
            "lat": pd.to_numeric(df["tile_y"], errors="coerce"),
            "lng": pd.to_numeric(df["tile_x"], errors="coerce"),
            "d_mbps": pd.to_numeric(df["avg_d_kbps"], errors="coerce") / 1000.0,
            "tests": pd.to_numeric(df["tests"], errors="coerce"),
        }
    )
    keep = out["lat"].between(-90, 90) & out["lng"].between(-180, 180) & (out["d_mbps"] > 0) & (out["tests"] > 0)
    return out[keep].reset_index(drop=True)


def load(settings: Settings, source: Source, sources: dict[str, Source]) -> pd.DataFrame:
    path = settings.raw(source.id) / source.files[0]
    table = pq.read_table(path, columns=COLUMNS)
    df = prepare(table.to_pandas())
    print(f"prep   {source.id}: {len(df)} tiles with tests, median download {df['d_mbps'].median():.1f} Mbps")
    return df
