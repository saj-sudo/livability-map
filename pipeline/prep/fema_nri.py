"""FEMA National Risk Index (census tracts) -> tract polygons with the expected annual building
loss rate across all 18 NRI hazards (SPEC §13.38, `nri` dimension, group env).

The NRI table carries ``ALR_VALB`` (expected annual loss rate, buildings: the share of building
value lost per year on average). Where that column is absent the rate is rebuilt from
``EAL_VALB / BUILDVALUE``. The rate is per dollar of buildings, so it does not grow with a
tract's size or wealth the way the dollar EAL and the composite RISK_SCORE do; RISK_SCORE also
folds in social vulnerability, which the map keeps out of a hazard reading.
"""

from __future__ import annotations

import zipfile

import numpy as np
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column

# Hazard-specific building loss rates, carried for `python -m pipeline.nri_check` (they are not a
# dimension). The NRI column names are from memory (SPEC §13.38, source still `verified: search`),
# so a table without them just yields a layer without these columns.
HAZARD_RATES = {"rflood_per_1k": "rfld_alrb", "cflood_per_1k": "cfld_alrb", "heat_per_1k": "hwav_alrb"}


def prepare(nri: pd.DataFrame) -> pd.DataFrame:
    """GEOID (11-digit tract FIPS), population, building loss in USD per 1,000 of value per year,
    and, when the table has them, the riverine, coastal and heat-wave rates the same way."""
    fips = find_column(nri.columns, "tractfips")
    pop = find_column(nri.columns, "population")
    out = pd.DataFrame({"GEOID": nri[fips].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(11), "population": pd.to_numeric(nri[pop], errors="coerce")})
    if "alr_valb" in {str(c).lower() for c in nri.columns}:
        rate = pd.to_numeric(nri[find_column(nri.columns, "alr_valb")], errors="coerce")
    else:
        eal = pd.to_numeric(nri[find_column(nri.columns, "eal_valb")], errors="coerce")
        value = pd.to_numeric(nri[find_column(nri.columns, "buildvalue")], errors="coerce")
        with np.errstate(divide="ignore", invalid="ignore"):
            rate = (eal / value).where(value > 0)
    out["loss_per_1k"] = 1000.0 * rate.where(rate >= 0)  # negative values are not losses: missing, never 0
    named = {str(c).lower(): c for c in nri.columns}
    for name, column in HAZARD_RATES.items():
        if column in named:  # exact name: a prefix match could pick a different measure
            hazard = pd.to_numeric(nri[named[column]], errors="coerce")
            out[name] = 1000.0 * hazard.where(hazard >= 0)  # not applicable stays missing, never 0
    return out.dropna(subset=["loss_per_1k"]).reset_index(drop=True)


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    archive = settings.raw(source.id) / source.files[0]
    with zipfile.ZipFile(archive) as z:
        members = [n for n in z.namelist() if n.lower().endswith(".csv") and "dictionary" not in n.lower()]
        if not members:
            raise FileNotFoundError(f"{archive.name}: no table CSV inside")
        with z.open(members[0]) as fh:
            nri = pd.read_csv(fh, dtype=str, low_memory=False, encoding_errors="replace")
    table = prepare(nri)
    tracts = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOID"]).to_crs(4326)
    merged = tracts.merge(table, on="GEOID", how="inner")
    print(f"prep   fema_nri: {len(merged)} tracts with a building loss rate ({len(table) - len(merged)} NRI rows without a 2025 polygon)")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
