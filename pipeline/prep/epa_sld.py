"""EPA Smart Location Database v3 -> block-group polygons with transit frequency (SPEC §20.6
transit). The File Geodatabase has one feature layer; ``D4C`` (transit trips per hour within
a quarter mile, evening peak) uses ``-99999`` for "no data", which becomes NaN (invariant 3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source

SENTINEL = -99999.0
COLUMNS = ["GEOID20", "D4C", "NatWalkInd", "TotPop"]


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ("D4C", "NatWalkInd", "TotPop"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
        out.loc[np.isclose(out[c], SENTINEL), c] = np.nan
    return out


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd
    import pyogrio

    gdb = rawfiles.resolve_vector(settings, source)
    layers = [name for name, _ in pyogrio.list_layers(gdb)]
    layer = layers[0] if len(layers) == 1 else next((n for n in layers if "SLD" in n.upper() or "SMART" in n.upper()), layers[0])
    gdf = gpd.read_file(gdb, layer=layer, columns=COLUMNS)
    gdf = prepare(gdf)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    print(f"prep   epa_sld: layer {layer}, {len(gdf)} block groups, D4C present for {int(gdf['D4C'].notna().sum())}")
    return gdf
