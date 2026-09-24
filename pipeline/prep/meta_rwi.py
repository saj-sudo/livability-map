"""Meta Data for Good Relative Wealth Index, 93 low- and middle-income countries (SPEC §13.36, §15).

The combined HDX file has one row per Bing zoom-14 tile (~2.4 km): ``latitude`` / ``longitude``
are the tile centre, ``rwi`` a standardised wealth index relative *within its country*, ``error``
the model's standard error. There is no country column; none is needed, because the dims stage
ranks each hex against the other hexes of its own country (``domain_by_country``), never against
the world. ``point_radius`` averages the tiles within a few km of each hex centre. CC BY-NC 4.0.
"""

from __future__ import annotations

import pandas as pd


def load_csv(path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(path_or_buffer, usecols=["latitude", "longitude", "rwi", "error"], dtype={"rwi": "float64", "error": "float64"})
    return df.rename(columns={"latitude": "lat", "longitude": "lng"})[["lat", "lng", "rwi", "error"]]


def load(settings, source, sources) -> pd.DataFrame:
    return load_csv(settings.raw(source.id) / source.files[0])
