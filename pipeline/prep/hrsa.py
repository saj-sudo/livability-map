"""HRSA Area Health Resources File -> county polygons with active physicians per 10,000
residents (SPEC §20.6 health, US joiner). County population comes from ACS B03002 county rows
so the denominator matches the rest of the US layers.
"""

from __future__ import annotations

import re
import zipfile

import numpy as np
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from . import acs
from .util import find_column


def _physician_column(columns) -> str:
    """Newest ``md_nf_activ_YY`` column (total active non-federal MDs)."""
    cands = sorted((c for c in columns if re.fullmatch(r"md_nf_activ_\d\d", str(c).lower())), key=lambda c: int(str(c)[-2:]))
    if not cands:
        raise KeyError("AHRF: no md_nf_activ_YY column found")
    return cands[-1]


def prepare(ahrf: pd.DataFrame, county_pop: pd.DataFrame) -> pd.DataFrame:
    fips = find_column(ahrf.columns, "fips_st_cnty")
    col = _physician_column(ahrf.columns)
    df = pd.DataFrame({"GEOID": ahrf[fips].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5), "md_active": pd.to_numeric(ahrf[col], errors="coerce")})
    df = df.merge(county_pop, on="GEOID", how="left")
    with np.errstate(divide="ignore", invalid="ignore"):
        df["physicians_per_10k"] = (1e4 * df["md_active"] / df["county_pop"]).where(df["county_pop"] > 0)
    return df.dropna(subset=["physicians_per_10k"]).reset_index(drop=True)


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    archive = settings.raw(source.id) / source.files[0]
    with zipfile.ZipFile(archive) as z:
        members = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not members:
            raise FileNotFoundError(f"{archive.name}: no CSV inside")
        with z.open(members[0]) as fh:
            ahrf = pd.read_csv(fh, dtype=str, low_memory=False, encoding_errors="replace")
    table = prepare(ahrf, acs.county_population(settings, sources))
    counties = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOID"]).to_crs(4326)
    merged = counties.merge(table, on="GEOID", how="inner")
    print(f"prep   hrsa_ahrf: {len(merged)} counties with physicians per 10k (column {_physician_column(ahrf.columns)})")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
