"""Urban Institute Education Data Portal EDFacts district graduation rates + NCES EDGE district
boundaries -> district polygons (SPEC §20.6 school).

The CSV has one row per district x subgroup; the all-students row has every subgroup code set
to 99. ``grad_rate_midpt`` is the midpoint of the published range; ``cohort_num`` weights the
overlay. Boundaries are joined on the 7-character LEAID (``GEOID`` in the NCES shapefile).
"""

from __future__ import annotations

import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column

SUBGROUPS = ["race", "lep", "homeless", "disability", "econ_disadvantaged", "foster_care"]
ALL_STUDENTS = 99


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for col in SUBGROUPS:
        if col in df.columns:
            mask &= pd.to_numeric(df[col], errors="coerce") == ALL_STUDENTS
    out = df[mask].copy()
    out["LEAID"] = out["leaid"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    out["grad_rate_midpt"] = pd.to_numeric(out["grad_rate_midpt"], errors="coerce")
    out["cohort_num"] = pd.to_numeric(out["cohort_num"], errors="coerce")
    out = out.dropna(subset=["grad_rate_midpt"]).drop_duplicates("LEAID")
    return out[["LEAID", "grad_rate_midpt", "cohort_num"]].reset_index(drop=True)


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    table = prepare(pd.read_csv(settings.raw(source.id) / source.files[0], dtype={"leaid": str}, low_memory=False))
    boundaries = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]))
    key = find_column(boundaries.columns, "GEOID", "LEAID")
    boundaries = boundaries[[key, "geometry"]].rename(columns={key: "LEAID"})
    boundaries["LEAID"] = boundaries["LEAID"].astype(str).str.zfill(7)
    if boundaries.crs is None:
        boundaries = boundaries.set_crs(4269)
    boundaries = boundaries.to_crs(4326)
    merged = boundaries.merge(table, on="LEAID", how="inner")
    print(f"prep   urban_edu_districts: {len(merged)} districts with graduation rates and boundaries (of {len(table)} rates, {len(boundaries)} polygons)")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
