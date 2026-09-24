"""Dutch CBS "Statistische gegevens per vierkant" (SPEC §13.34, §15), 2023 complete release.

Each download is a zip with one GeoPackage of square polygons in RD New (EPSG:28992). Counts
are rounded to 5 and percentages to 10; ``-99997`` means 0-4 / confidential / not present and
``-99995`` "published in a later version", so every value <= -99995 becomes missing (never 0).
The loaders return one point per square (its centre in WGS84) for the ``point_mean`` joiner:

- 100 m squares: ``woz_keur`` (average provisional WOZ home value, thousand EUR) weighted by
  ``homes`` (dwellings), feeding ``rent`` as a housing-cost level;
- 500 m squares: ``low_income_share`` (% of households in the national bottom 40% of
  disposable income; CBS publishes income only at 500 m) weighted by ``households``, feeding
  ``incmix``.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

SENTINEL_MAX = -99995  # -99995 later version, -99997 0-4 / secret / not present

COLUMNS_100M = {"gemiddelde_woz_waarde_woning": "woz_keur", "aantal_woningen": "homes"}
COLUMNS_500M = {"percentage_laag_inkomen_huishouden": "low_income_share", "aantal_part_huishoudens": "households"}


def load_squares(path, layer: str, columns: dict[str, str]) -> pd.DataFrame:
    gdf = gpd.read_file(path, layer=layer, columns=list(columns))
    missing = [c for c in columns if c not in gdf.columns]
    if missing:
        raise KeyError(f"CBS squares ({layer}): columns {missing} not found; the published layout may have changed (SPEC §15)")
    centres = gdf.geometry.centroid.to_crs(4326)
    out = pd.DataFrame({"lat": centres.y.to_numpy(), "lng": centres.x.to_numpy()})
    for src, dst in columns.items():
        v = pd.to_numeric(gdf[src], errors="coerce").astype("float64")
        out[dst] = v.where(v > SENTINEL_MAX, np.nan).to_numpy()
    return out


def _zip_path(settings, source) -> str:
    raw = settings.raw(source.id) / source.files[0]
    return f"zip://{raw.as_posix()}!{source.extra['member']}"


def load_100m(settings, source, sources) -> pd.DataFrame:
    return load_squares(_zip_path(settings, source), source.extra["layer"], COLUMNS_100M)


def load_500m(settings, source, sources) -> pd.DataFrame:
    return load_squares(_zip_path(settings, source), source.extra["layer"], COLUMNS_500M)
