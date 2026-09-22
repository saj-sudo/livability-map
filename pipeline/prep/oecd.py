"""OECD Regional Well-Being (TL2) -> TL2 polygons with Jobs / Housing / Health scores
(SPEC §20.6 jobs, house, health; OECD domain).

OECD publishes no TL2 polygons (SPEC §13.21), so the geometry is derived: the OECD Territorial
correspondence table lists TL2 regions and their TL3 children by name per ISO3, and geoBoundaries
ADM1 polygons are matched to those names. Per country the TL2 names are tried first; when fewer
than 60% match, TL3 names are matched instead and dissolved up to their TL2 parent (Japan's
prefectures -> regions, for example). ``pipeline/crosswalks/oecd_tl2_adm1.csv`` holds manual
overrides. Unmatched regions are reported and left out (they stay ``none`` on the map).

Output: ``Code, Region, ISO3, jobs_score, housing_burden, health_score, geometry``.
``housing_burden = 10 - Housing`` so that higher is worse like the US rent-burden construct.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..config import Settings
from ..registry import Source
from .util import find_column, normalize_name, read_xlsx

CORRESPONDENCE_SOURCE = "oecd_tl2_correspondence"
ADM1_SOURCE = "geoboundaries_adm1"
MIN_TL2_MATCH = 0.6
FUZZY_CUTOFF = 0.85


def match_names(targets: dict[str, list[str]], candidates: dict[int, str]) -> dict[str, int]:
    """Best 1:1 assignment of target ids to candidate rows by normalised name (exact first,
    then close matches). ``targets``: id -> name variants; ``candidates``: row index -> name."""
    norm_cands: dict[str, int] = {}
    for idx, name in candidates.items():
        key = normalize_name(name)
        if key and key not in norm_cands:
            norm_cands[key] = idx
    taken: set[int] = set()
    out: dict[str, int] = {}
    for tid, names in targets.items():
        keys = [normalize_name(n) for n in names if isinstance(n, str) and n.strip()]
        keys = [k for k in keys if k]
        hit = None
        for k in keys:
            if k in norm_cands and norm_cands[k] not in taken:
                hit = norm_cands[k]
                break
        if hit is None:
            for k in keys:
                close = difflib.get_close_matches(k, list(norm_cands), n=3, cutoff=FUZZY_CUTOFF)
                free = [c for c in close if norm_cands[c] not in taken]
                if free:
                    hit = norm_cands[free[0]]
                    break
        if hit is not None:
            out[tid] = hit
            taken.add(hit)
    return out


def _overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["tl2_code", "iso3", "shape_name"])
    df = pd.read_csv(path, dtype=str, comment="#").fillna("")
    return df[df["tl2_code"] != ""]


def build_tl2_geometry(corr: pd.DataFrame, adm1: gpd.GeoDataFrame, overrides: pd.DataFrame | None = None) -> tuple[gpd.GeoDataFrame, dict]:
    """Pure crosswalk (unit-tested on synthetic frames). ``corr`` needs columns ISO3, REG_ID, TL,
    PARENT, NAME_ENG, NAME_ORIG, NAME_PUB; ``adm1`` needs shapeGroup, shapeName, geometry."""
    overrides = overrides if overrides is not None else pd.DataFrame(columns=["tl2_code", "iso3", "shape_name"])
    tl2 = corr[corr["TL"] == 2]
    tl3 = corr[corr["TL"] == 3]
    rows = []
    report: dict[str, dict] = {}
    for iso3 in sorted(tl2["ISO3"].dropna().unique()):
        t2 = tl2[tl2["ISO3"] == iso3]
        cands_df = adm1[adm1["shapeGroup"] == iso3]
        info = {"tl2": int(len(t2)), "matched": 0, "method": "none", "unmatched": []}
        if cands_df.empty:
            info["unmatched"] = t2["REG_ID"].tolist()
            report[iso3] = info
            continue
        cands = {int(i): str(n) for i, n in zip(cands_df.index, cands_df["shapeName"], strict=True)}
        names2 = {r.REG_ID: [r.NAME_ENG, r.NAME_ORIG, r.NAME_PUB] for r in t2.itertuples()}
        m2 = match_names(names2, cands)
        assignment: dict[str, list[int]] = {k: [v] for k, v in m2.items()}
        method = "tl2"
        if len(m2) / max(1, len(t2)) < MIN_TL2_MATCH:
            t3 = tl3[(tl3["ISO3"] == iso3) & tl3["PARENT"].isin(t2["REG_ID"])]
            names3 = {r.REG_ID: [r.NAME_ENG, r.NAME_ORIG, r.NAME_PUB] for r in t3.itertuples()}
            m3 = match_names(names3, cands)
            grouped: dict[str, list[int]] = {}
            parent_of = dict(zip(t3["REG_ID"], t3["PARENT"], strict=True))
            for tid, idx in m3.items():
                grouped.setdefault(parent_of[tid], []).append(idx)
            if len(grouped) > len(m2):
                assignment, method = grouped, "tl3"
        # manual overrides win: tl2_code -> one or more ADM1 shape names
        ov = overrides[overrides["iso3"] == iso3]
        for code, group in ov.groupby("tl2_code"):
            idxs = [i for i, n in cands.items() if n in set(group["shape_name"])]
            if idxs:
                assignment[code] = idxs
                method = method if method != "none" else "override"
        for code, idxs in assignment.items():
            geom = cands_df.loc[idxs, "geometry"].union_all() if len(idxs) > 1 else cands_df.loc[idxs[0], "geometry"]
            region = t2.loc[t2["REG_ID"] == code, "NAME_ENG"]
            rows.append({"Code": code, "ISO3": iso3, "Region": region.iloc[0] if len(region) else code, "method": method, "geometry": geom})
        info["matched"] = len(assignment)
        info["method"] = method
        info["unmatched"] = sorted(set(t2["REG_ID"]) - set(assignment))
        report[iso3] = info
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=adm1.crs or 4326) if rows else gpd.GeoDataFrame(columns=["Code", "ISO3", "Region", "method", "geometry"], geometry="geometry", crs=4326)
    return gdf, report


def read_correspondence(path: Path, sheet: str, header_row: int) -> pd.DataFrame:
    """The TL2024 sheet has title rows above the header; locate the row that holds ISO3 / REG_ID
    instead of trusting a fixed row number (it moved between file versions)."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None, nrows=12, engine="openpyxl")
    hits = [i for i in range(len(raw)) if {"ISO3", "REG_ID"} <= {str(v).strip() for v in raw.iloc[i].tolist()}]
    header_row = (hits[0] + 1) if hits else header_row
    df = read_xlsx(path, sheet, header_row)
    iso = find_column(df.columns, "ISO3")
    reg = find_column(df.columns, "REG_ID")
    tl = find_column(df.columns, "TL")
    parent = find_column(df.columns, "Hierarchical relations")
    eng = find_column(df.columns, "Name (eng)")
    orig = find_column(df.columns, "Name (orig)")
    pub = find_column(df.columns, "Name (publication-eng)")
    out = df[[iso, reg, tl, parent, eng, orig, pub]].copy()
    out.columns = ["ISO3", "REG_ID", "TL", "PARENT", "NAME_ENG", "NAME_ORIG", "NAME_PUB"]
    out["TL"] = pd.to_numeric(out["TL"], errors="coerce")
    return out.dropna(subset=["REG_ID", "TL"])


def tl2_geometry(settings: Settings, sources: dict[str, Source]) -> gpd.GeoDataFrame:
    corr_src = sources[CORRESPONDENCE_SOURCE]
    corr = read_correspondence(settings.raw(corr_src.id) / corr_src.files[0], corr_src.extra.get("sheet", "Regions TL2024"), int(corr_src.extra.get("header_row", 4)))
    adm1_src = sources[ADM1_SOURCE]
    adm1 = gpd.read_file(settings.raw(adm1_src.id) / adm1_src.files[0], columns=["shapeGroup", "shapeName"]).to_crs(4326)
    overrides = _overrides(settings.root / "pipeline" / "crosswalks" / "oecd_tl2_adm1.csv")
    gdf, report = build_tl2_geometry(corr, adm1, overrides)
    total = sum(v["tl2"] for v in report.values())
    matched = sum(v["matched"] for v in report.values())
    worst = sorted(((v["matched"] / max(1, v["tl2"]), k) for k, v in report.items()))[:8]
    print(f"prep   oecd tl2: {matched}/{total} TL2 regions geolocated ({100 * matched / max(1, total):.0f}%); weakest: " + ", ".join(f"{k} {100 * r:.0f}%" for r, k in worst))
    out = settings.cache_dir / "prep" / "oecd_tl2_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"total": total, "matched": matched, "countries": report}, indent=2), encoding="utf-8")
    return gdf


def load(settings: Settings, source: Source, sources: dict[str, Source]) -> gpd.GeoDataFrame:
    path = settings.raw(source.id) / source.files[0]
    df = read_xlsx(path, source.extra.get("sheet", "Score_Last"), int(source.extra.get("header_row", 7)))
    code = find_column(df.columns, "Code")
    region = find_column(df.columns, "Region")
    jobs, housing, health = (find_column(df.columns, c) for c in ("Jobs", "Housing", "Health"))
    table = df[[code, region, jobs, housing, health]].copy()
    table.columns = ["Code", "Region", "Jobs", "Housing", "Health"]
    for c in ("Jobs", "Housing", "Health"):
        table[c] = pd.to_numeric(table[c], errors="coerce")
    table = table.dropna(subset=["Code"])
    table["Code"] = table["Code"].astype(str).str.strip()
    table["jobs_score"] = table["Jobs"]
    table["housing_burden"] = 10.0 - table["Housing"]
    table["health_score"] = table["Health"]
    geom = tl2_geometry(settings, sources)
    merged = geom.merge(table[["Code", "Region", "jobs_score", "housing_burden", "health_score"]], on="Code", how="inner", suffixes=("_corr", ""))
    print(f"prep   oecd_regional_wellbeing: {len(merged)} TL2 regions with scores and polygons (of {len(table)} in the data file)")
    keep = ["Code", "Region", "ISO3", "method", "jobs_score", "housing_burden", "health_score", "geometry"]
    return gpd.GeoDataFrame(merged[keep], geometry="geometry", crs=4326)
