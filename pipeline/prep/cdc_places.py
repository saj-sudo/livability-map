"""CDC PLACES census-tract estimates (GIS-friendly wide format) -> tract polygons with the share
of adults reporting fair or poor health (SPEC §13.38, `phealth` dimension).

PLACES models BRFSS answers down to tracts; the wide file has one row per tract with
``TractFIPS``, ``TotalPopulation`` and ``<MEASURE>_CrudePrev`` columns. GHLTH is "fair or poor
self-rated health status among adults 18+", the broadest single outcome measure. Tracts that
PLACES leaves blank (very small populations) stay missing.
"""

from __future__ import annotations

import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column


def prepare(places: pd.DataFrame) -> pd.DataFrame:
    """GEOID (11-digit tract FIPS), population, % of adults in fair or poor health."""
    fips = find_column(places.columns, "tractfips", "locationname")
    pop = find_column(places.columns, "totalpopulation")
    prev = find_column(places.columns, "ghlth_crudeprev")
    out = pd.DataFrame(
        {
            "GEOID": places[fips].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(11),
            "population": pd.to_numeric(places[pop].astype(str).str.replace(",", ""), errors="coerce"),
            "poor_health_pct": pd.to_numeric(places[prev], errors="coerce"),
        }
    )
    out = out[out["poor_health_pct"].between(0, 100)]
    return out.drop_duplicates("GEOID").reset_index(drop=True)


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    path = settings.raw(source.id) / source.files[0]
    table = prepare(pd.read_csv(path, dtype=str, low_memory=False, encoding_errors="replace"))
    tracts = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOID"]).to_crs(4326)
    merged = tracts.merge(table, on="GEOID", how="inner")
    # PLACES uses 2020 tracts; the 2025 cartographic file is the same vintage, so the join loss is small
    print(f"prep   cdc_places: {len(merged)} tracts with fair-or-poor health ({len(table) - len(merged)} PLACES rows without a polygon)")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
