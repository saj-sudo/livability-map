"""Opportunity Atlas (Opportunity Insights) tract outcomes -> 2020 tract polygons with two
measures of how children who grew up in the tract did as adults (SPEC §13.48, `opp`, `opp25`).

Both are household income ranks (0-1, national rank within the birth cohort) of children born
1978-1983 at about age 31-37 (incomes around 2014-2015), pooled over races and genders:

- ``kfr_pooled_pooled_mean`` -> ``kfr_pooled`` (`opp`): children of all parent incomes. It
  partly reflects where well-off families already live, not only upward mobility.
- ``kfr_pooled_pooled_p25`` -> ``kfr_p25`` (`opp25`): the predicted rank of children whose
  parents were at the 25th income percentile, the standard upward-mobility measure.

The Atlas uses 2010 census tracts; the map's tract polygons (``cb_tracts``) are 2020 tracts. The
Census Bureau's 2020-to-2010 tract relationship file (public domain, pipe-delimited, one row per
2020 x 2010 overlap with ``AREALAND_PART``) carries the values across: each 2020 tract takes the
**land-area-weighted** mean of the 2010 tracts it overlaps (the file has no population, so the
weights are overlap land areas; water-only tracts use total overlap area). Each measure keeps a
value only where 2010 tracts with that value cover at least half of the 2020 tract's land
(``MIN_SHARE``); suppressed or absent 2010 values stay missing, never 0. The layer also carries
``children``: the Atlas child count apportioned by land share when the file has one
(``kfr_pooled_pooled_n``), else the 2020 tract's land area, so the hex overlay weights by
children or, failing that, by area.

Column names and the file layout are from memory (both sources ``verified: search``); the loader
stops with the columns it found when they differ.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import rawfiles
from ..config import Settings
from ..registry import Source
from .util import find_column

# Atlas column -> (prepared 2010 column, crosswalked layer column, what it is)
MEASURES = {
    "kfr_pooled_pooled_mean": ("kfr", "kfr_pooled", "all parents, all races and genders"),
    "kfr_pooled_pooled_p25": ("kfr25", "kfr_p25", "parents at the 25th percentile, all races and genders"),
}
MEASURE = "kfr_pooled_pooled_mean"  # the all-parents measure (kept for callers that name one)
COUNT_CANDIDATES = ("kfr_pooled_pooled_n", "count_pooled", "kid_count", "n_pooled")
MIN_SHARE = 0.5  # share of a 2020 tract's land that valued 2010 tracts must cover


def _geoid(s: pd.Series, width: int) -> pd.Series:
    """Zero-pad numeric ids ("1001020100" -> "01001020100"); leave anything else as it is."""
    t = s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    return t.where(~t.str.fullmatch(r"\d+"), t.str.zfill(width))


def prepare(atlas: pd.DataFrame) -> pd.DataFrame:
    """Atlas rows -> ``GEOID10``, ``kfr`` and ``kfr25`` (0-1 ranks) and ``n`` (children, NaN
    without a count column). The tract id is built from ``state`` + ``county`` + ``tract`` or
    read from one 11-digit column. Both measures must be present; a missing one stops the run
    with the kfr columns the file has."""
    lower = {str(c).lower().strip(): c for c in atlas.columns}
    absent = [m for m in MEASURES if m not in lower]
    if absent:
        kfr = [c for c in atlas.columns if str(c).lower().startswith("kfr")]
        wanted = "; ".join(f"{m!r} ({MEASURES[m][2]})" for m in absent)
        raise KeyError(f"Opportunity Atlas: missing {wanted}; kfr columns found: {kfr[:20] or 'none'}; all columns: {list(atlas.columns)[:30]}")
    if {"state", "county", "tract"} <= set(lower):
        geoid = _geoid(atlas[lower["state"]], 2) + _geoid(atlas[lower["county"]], 3) + _geoid(atlas[lower["tract"]], 6)
    else:
        try:
            geoid = _geoid(atlas[find_column(atlas.columns, "geoid", "tract_fips", "tractfips", "tract_id", "geoid10")], 11)
        except KeyError:
            raise KeyError(f"Opportunity Atlas: need state, county and tract columns or one tract id column (geoid / tract_fips); columns found: {list(atlas.columns)[:30]}") from None
    out = pd.DataFrame({"GEOID10": geoid})
    for col, (short, _, _) in MEASURES.items():
        v = pd.to_numeric(atlas[lower[col]], errors="coerce")
        out[short] = v.where(v.between(0, 1))  # blank or impossible ranks are missing, never 0
    count = next((lower[c] for c in COUNT_CANDIDATES if c in lower), None)
    n = pd.to_numeric(atlas[count], errors="coerce") if count else pd.Series(np.nan, index=atlas.index)
    out["n"] = n.where(n >= 0)
    shorts = [s for s, _, _ in MEASURES.values()]
    return out.dropna(subset=shorts, how="all").drop_duplicates("GEOID10").reset_index(drop=True)


def read_relationship(rel: pd.DataFrame) -> pd.DataFrame:
    """The 2020-to-2010 tract relationship table -> ``GEOID``, ``GEOID10``, ``land`` (overlap
    land area), ``water`` (overlap water area) and ``land10`` (the 2010 tract's land area, NaN
    when the file lacks it)."""
    cols = [str(c).strip().lstrip("﻿") for c in rel.columns]
    rel = rel.set_axis(cols, axis=1)
    try:
        g20 = find_column(cols, "geoid_tract_20", "geoid_20", "geoid20", "tract20")
        g10 = find_column(cols, "geoid_tract_10", "geoid_10", "geoid10", "tract10")
        land = find_column(cols, "arealand_part", "aland_part", "land_part")
    except KeyError:
        raise KeyError(f"tract relationship file: expected GEOID_TRACT_20, GEOID_TRACT_10 and AREALAND_PART; columns found: {cols[:30]}") from None
    water = next((c for c in cols if c.lower() in ("areawater_part", "awater_part", "water_part")), None)
    land10 = next((c for c in cols if c.lower() in ("arealand_tract_10", "aland_tract_10", "arealand_10")), None)
    return pd.DataFrame(
        {
            "GEOID": _geoid(rel[g20], 11),
            "GEOID10": _geoid(rel[g10], 11),
            "land": pd.to_numeric(rel[land], errors="coerce").fillna(0.0),
            "water": pd.to_numeric(rel[water], errors="coerce").fillna(0.0) if water else 0.0,
            "land10": pd.to_numeric(rel[land10], errors="coerce") if land10 else np.nan,
        }
    )


def crosswalk(values10: pd.DataFrame, rel: pd.DataFrame, min_share: float = MIN_SHARE) -> pd.DataFrame:
    """2010-tract values onto 2020 tracts (``GEOID``, ``kfr_pooled``, ``kfr_p25``, ``children``):
    per measure, the overlap land-area-weighted mean over 2010 tracts with a value, kept where
    those cover at least ``min_share`` of the 2020 tract's land; a 2020 tract with no land weights
    by total area. A 2020 tract with neither measure is left out."""
    r = rel.copy()
    tract_land = r.groupby("GEOID")["land"].transform("sum")
    r["w"] = np.where(tract_land > 0, r["land"], r["land"] + r["water"])
    r["wall"] = r.groupby("GEOID")["w"].transform("sum")
    r = r.merge(values10, on="GEOID10", how="left")
    cols = {}
    for short, layer_col, _ in MEASURES.values():
        if short not in r.columns:
            continue
        valued = r[r[short].notna() & (r["w"] > 0)]
        g = valued.assign(wv=valued["w"] * valued[short]).groupby("GEOID").agg(wv=("wv", "sum"), w=("w", "sum"), wall=("wall", "first"))
        keep = g["w"] / g["wall"] >= min_share - 1e-9
        cols[layer_col] = (g["wv"] / g["w"])[keep]
    out = pd.DataFrame(cols)
    out = out.dropna(how="all").rename_axis("GEOID").reset_index()
    if values10["n"].notna().any():
        # children apportioned by the overlap's share of the 2010 tract's land (from the file, or
        # summed over its overlaps when the file has no 2010 land area column)
        land10 = r["land10"].where(r["land10"] > 0, r.groupby("GEOID10")["land"].transform("sum"))
        with np.errstate(divide="ignore", invalid="ignore"):
            r["kids"] = r["n"] * (r["land"] / land10).where(land10 > 0)
        out["children"] = out["GEOID"].map(r.groupby("GEOID")["kids"].sum(min_count=1))
    else:
        out["children"] = out["GEOID"].map(r.groupby("GEOID")["land"].sum())  # area weighting
    layer_cols = [c for _, c, _ in MEASURES.values()]
    return out.reindex(columns=["GEOID", *layer_cols, "children"]).reset_index(drop=True)


def read_atlas(path) -> pd.DataFrame:
    """The Atlas CSV, reading only the id, measure and count columns (the full outcomes file has
    thousands of columns); a file without the measures is read in part so ``prepare`` can list
    what it has."""
    header = [str(c).strip() for c in pd.read_csv(path, nrows=0, encoding_errors="replace").columns]
    if not set(MEASURES) <= {c.lower() for c in header}:
        return pd.read_csv(path, nrows=5, dtype=str, encoding_errors="replace")
    keep = {"state", "county", "tract", "geoid", "tract_fips", "tractfips", "tract_id", "geoid10", *MEASURES, *COUNT_CANDIDATES}
    return pd.read_csv(path, usecols=lambda c: str(c).strip().lower() in keep, dtype=str, low_memory=False, encoding_errors="replace")


def read_rel_file(path) -> pd.DataFrame:
    return pd.read_csv(path, sep="|", dtype=str, encoding="utf-8-sig", low_memory=False)


def load(settings: Settings, source: Source, sources: dict[str, Source]):
    import geopandas as gpd

    atlas = prepare(read_atlas(settings.raw(source.id) / source.files[0]))
    rel_src = sources[source.extra["also_needs"][0]]
    rel = read_relationship(read_rel_file(settings.raw(rel_src.id) / rel_src.files[0]))
    table = crosswalk(atlas, rel)
    weights = "children apportioned by land share" if atlas["n"].notna().any() else "2020 tract land area (no child count column)"
    tracts = gpd.read_file(rawfiles.resolve_vector(settings, sources[source.extra["geometry"]]), columns=["GEOID"]).to_crs(4326)
    merged = tracts.merge(table, on="GEOID", how="inner")
    filled = ", ".join(f"{c} {int(merged[c].notna().sum())}" for _, c, _ in MEASURES.values())
    print(
        f"prep   opp_atlas: {len(atlas)} 2010 tracts -> {len(table)} 2020 tracts (land-area-weighted; hex weights: {weights}); "
        f"{len(merged)} with a polygon ({filled}; {len(table) - len(merged)} without one; Connecticut's 2020 tract ids probably changed with its 2022 planning regions)"
    )
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
