"""UCDP Georeferenced Event Dataset, global 26.1 (SPEC §13.36, §15): organised-violence events.

Kept: events of the last ten complete years (``YEARS``) located to the exact place, within 25 km
of a known point, or to a second-order administrative unit (``where_prec`` 1-3, 85% of events).
Events known only to an admin1 or country centroid, a fuzzy area or international waters
(``where_prec`` 4-7) are dropped: summing them at a centroid would invent a hotspot. Each event
becomes a point carrying ``fatal_per_year`` = best fatality estimate / number of years, so a
``point_radius`` sum gives conflict deaths per year within the radius. CC BY 4.0.
"""

from __future__ import annotations

import zipfile

import pandas as pd

YEARS = range(2016, 2026)  # 2016-2025, the ten complete years in GED 26.1
MAX_WHERE_PREC = 3
MEMBER = "GEDEvent_v26_1.csv"


def load_frame(df: pd.DataFrame) -> pd.DataFrame:
    keep = df["year"].isin(list(YEARS)) & (pd.to_numeric(df["where_prec"], errors="coerce") <= MAX_WHERE_PREC)
    d = df[keep]
    return pd.DataFrame(
        {
            "lat": pd.to_numeric(d["latitude"], errors="coerce").to_numpy(),
            "lng": pd.to_numeric(d["longitude"], errors="coerce").to_numpy(),
            "fatal_per_year": pd.to_numeric(d["best"], errors="coerce").to_numpy() / len(YEARS),
        }
    )


def load_zip(path, member: str = MEMBER) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf, zf.open(member) as fh:
        df = pd.read_csv(fh, usecols=["year", "where_prec", "best", "latitude", "longitude"], low_memory=False)
    return load_frame(df)


def load(settings, source, sources) -> pd.DataFrame:
    return load_zip(settings.raw(source.id) / source.files[0], source.extra.get("member", MEMBER))
