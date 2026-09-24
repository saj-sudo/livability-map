"""Water Point Data Exchange, WPdx+ (SPEC §13.37, §15): community water points, 19 countries.

WPdx+ keeps the latest record of each water point (440k points). Column names mostly carry an
HXL ``#`` prefix, which is stripped. ``status_id`` says whether water was available when the
point was last visited (Yes / No / Unknown); Unknown rows and rows flagged ``is_duplicate`` are
dropped, and ``has_water`` is 1 for Yes, 0 for No. ``point_radius`` averages it within 5 km, so a
hex's value is the share of recorded water points nearby that had water at the last visit. Where
no point is recorded nearby the value is missing: WPdx records community points, mostly outside
piped networks, so "no point" never means "no water". Licence: CC BY-SA 4.0 as WPdx publishes it
on HDX (providers license their data to WPdx under CC BY 4.0); derived water_* values are
labelled share-alike.
"""

from __future__ import annotations

import pandas as pd

COLUMNS = ["lat_deg", "lon_deg", "status_id", "is_duplicate"]


def load_csv(path) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=lambda c: c.lstrip("#") in COLUMNS, dtype=str, low_memory=False)
    df.columns = [c.lstrip("#") for c in df.columns]
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"WPdx: columns {missing} not found; the export layout may have changed (SPEC §15)")
    df = df[df["is_duplicate"].str.lower() != "true"]
    status = df["status_id"].str.strip().str.lower()
    df = df[status.isin(["yes", "no"])]
    return pd.DataFrame(
        {
            "lat": pd.to_numeric(df["lat_deg"], errors="coerce").to_numpy(),
            "lng": pd.to_numeric(df["lon_deg"], errors="coerce").to_numpy(),
            "has_water": (status[df.index] == "yes").astype("float64").to_numpy(),
        }
    )


def load(settings, source, sources) -> pd.DataFrame:
    return load_csv(settings.raw(source.id) / source.files[0])
