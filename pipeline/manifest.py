"""``manifest.json`` (SPEC §6.3): every source, every dimension, coverage, spot checks, notes.

Written by ``export`` to ``data/out/manifest.json``; ``tiles`` adds the tile archive entry and
``publish`` stamps the publication. The web app renders /methodology from it and the inspector
reads its ``sources`` list, so anything a person should be able to check lives here.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from . import sanity, timing
from .attrs import HAZARD_IDS, HAZARD_RAW
from .config import NON_COMMERCIAL, Settings
from .registry import Dimension, Source, load_dimensions, load_sources
from .stages.fetch import read_checksums

PROCESSING_NOTES = [
    "heat: World Bank CCKP CMIP6 ensemble median, SSP2-4.5, 2040-2059 climatology of days with Tmax > 35C, sampled at the hex centroid (the 0.25 degree pixel is coarser than the hex).",
    "riverine flood: WRI Aqueduct Floods RCP4.5 2050 1-in-100 inundation depth; pixel-wise median across five climate models, then the share of the hex's valid ~1 km pixels with depth >= 0.15 m.",
    "coastal flood: WRI Aqueduct Floods RCP4.5 2050 1-in-100 with subsidence, median sea-level rise; share of pixels with depth >= 0.15 m.",
    "water stress: WRI Aqueduct 4.0 future (2050, business-as-usual) water stress category 0-4 of the basin/province polygon under the hex centroid; -1 (arid and low water use) is shown but not scored.",
    "scores: every score is the midrank percentile (0-100) of the raw value among inhabited hexes at the same H3 resolution; life dimensions are ranked within their scoring domain (global, OECD, US, EU or England) so a US-only value is never ranked against the world. A derived resolution (res 6, 7) is ranked against the inhabited hexes of the finest complete resolution (res 5) in the same domain, so a neighbourhood keeps its colour meaning at every zoom. Higher score = more of the raw quantity; whether that is good is stated per dimension, and a source whose raw value runs the other way (IoD deprivation feeding jobs) has its percentile reflected so the dimension's direction holds.",
    "wellbeing: min-max normalised within its source (Subnational HDI across regions, World Happiness Report life evaluation across countries), never mixed; a source with a single distinct value scores 50.",
    "exposure: mean of the available hazard scores; coverage counts how many of the four hazards had data. Missing layers are excluded, never treated as 0.",
    "bivariate class: terciles of exposure and wellbeing over inhabited hexes; class = 1 + exposure tercile + 3 x wellbeing tercile (1 = low exposure, low wellbeing; 3 = high exposure, low wellbeing; 7 = low exposure, high wellbeing; 9 = high, high); 0 when either side is missing.",
    "uninhabited hexes (population below 100) keep their raw values and are scored against the inhabited distribution; the map hides them by default.",
    "population is the one attribute where no data is recorded as 0 (a count); hexes with no GHSL pixels are uninhabited.",
    "grid: H3 cells whose centre lies on Natural Earth 1:10m land; small islands and thin coasts without a cell centre on land are absent (a known gap). Res 6 and 7 (the resolution plan) are the H3 children of parent cells inside the listed countries or touching GHS-SMOD urban clusters / centres; a refined parent carries ref = true and is hidden where its children's layer is on screen.",
    "resolution: hazards are computed per hex; wellbeing and life dimensions are attached at the best available coarser resolution and tagged (admin1 | county | tract | national | none), never aggregated to hide within-region variation.",
]


def _source_entry(src: Source, checksums: dict[tuple[str, str], str]) -> dict:
    d = src.to_manifest()
    d["verified"] = str(src.extra.get("verified", "none"))
    d["checksums"] = {f: checksums[(src.id, f)] for f in src.files if (src.id, f) in checksums}
    d.pop("recipe", None)
    return d


def _coverage(df: pd.DataFrame, inhabited: pd.Series, dim: Dimension) -> dict:
    col = f"{dim.id}_res"
    if col not in df.columns:
        return {}
    tags = df.loc[inhabited, col].fillna("none").value_counts()
    return {str(k): int(v) for k, v in tags.items()}


def _domains(df: pd.DataFrame, inhabited: pd.Series, dim: Dimension) -> dict:
    col = f"{dim.id}_dom"
    if col not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df.loc[inhabited, col].dropna().value_counts().items()}


def _known_gaps(df: pd.DataFrame, inhabited: pd.Series, dims: list[Dimension]) -> dict:
    """Countries where an entire inhabited population has no value for a dimension."""
    gaps: dict[str, dict] = {}
    if "iso_a2" not in df.columns:
        return gaps
    inh = df[inhabited]
    for dim in dims:
        col = f"{dim.id}_res"
        if col not in inh.columns:
            continue
        missing = inh[col].fillna("none") == "none"
        by_country = missing.groupby(inh["iso_a2"]).mean()
        fully = sorted(by_country[by_country >= 0.999].index.dropna().tolist())
        gaps[dim.id] = {"countries_without_data": fully[:40], "n_countries_without_data": len(fully), "share_inhabited_hexes_missing": round(float(missing.mean()), 4) if len(inh) else None}
    for hz in HAZARD_IDS:
        col = f"{hz}_ok"
        if col in inh.columns:
            gaps[hz] = {"inhabited_hexes_without_data": int((~inh[col].fillna(False)).sum())}
    return gaps


def _spot_rows(df: pd.DataFrame, res: int, spots) -> list[dict]:
    keep = ["iso_a2", "admin1_name", "population", "inhabited"] + [HAZARD_RAW[h] for h in HAZARD_IDS] + [f"{h}_score" for h in HAZARD_IDS]
    keep += ["coverage", "exposure", "wb_value", "wb_score", "wb_source", "wb_res", "bivar"]
    rows = []
    for spot in spots:
        found = sanity.spot_row(df, res, spot)
        if found is None:
            rows.append({"name": spot.name, "expect": spot.expect, "found": False})
            continue
        cell, note, row = found
        rows.append({"name": spot.name, "expect": spot.expect, "found": True, "h3": cell, "note": note.strip(" ()"), **{k: row[k] for k in keep if k in row}})
    return rows


def build(settings: Settings) -> dict:
    sources = load_sources(settings.sources_path)
    dims = load_dimensions(settings.dimensions_path, sources)
    checksums = read_checksums(settings.raw_dir / "CHECKSUMS")
    life = [d for d in dims.values() if d.group != "hazard"]
    manifest: dict = {
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "h3_res": list(settings.res),
        "resolution_plan": [{**e.to_manifest(), "cells": (int(len(pd.read_parquet(settings.hexes_path(e.res), columns=["h3"]))) if settings.hexes_path(e.res).exists() else None)} for e in settings.plan.entries],
        "scenario": settings.scenario,
        "horizon": settings.horizon,
        "non_commercial": NON_COMMERCIAL,
        "fixtures": settings.fixtures,
        "bbox": list(settings.bbox) if settings.bbox else None,
        "tiles": {},
        "sources": [_source_entry(s, checksums) for s in sources.values()],
        "hazards": [{**dims[h].to_manifest(), "raw": HAZARD_RAW[h]} for h in HAZARD_IDS if h in dims],
        "dimensions": [],
        "coverage_summary": {},
        "spot_checks": {},
        "processing_notes": list(PROCESSING_NOTES),
        "known_gaps": {},
        "timings": timing.read(settings),
    }
    if settings.fixtures:
        from .fixtures import make_fixtures

        spots = make_fixtures.SPOT_CHECKS
    else:
        spots = sanity.SPOT_CHECKS
    dim_entries = {d.id: {**d.to_manifest(), "coverage": {}, "domains": {}} for d in life}
    for res in settings.res:
        if not settings.hexes_path(res).exists():
            continue
        df = sanity.load_merged(settings, res)
        inhabited = df["inhabited"].fillna(False).astype(bool) if "inhabited" in df.columns else pd.Series(True, index=df.index)
        summary = {"hexes_total": int(len(df)), "hexes_inhabited": int(inhabited.sum())}
        if "coverage" in df.columns:
            cov = df.loc[inhabited, "coverage"]
            summary["hexes_full_coverage"] = int((cov == 4).sum())
            summary["share_inhabited_coverage4"] = round(float((cov == 4).mean()), 4) if len(cov) else None
            summary["share_inhabited_coverage0"] = round(float((cov == 0).mean()), 4) if len(cov) else None
        if "wb_res" in df.columns:
            tags = df.loc[inhabited, "wb_res"].fillna("none").value_counts()
            for tag in ("admin1", "national", "none"):
                summary[f"wb_{tag}"] = int(tags.get(tag, 0))
        if "bivar" in df.columns:
            summary["bivar_counts"] = {str(int(k)): int(v) for k, v in df.loc[inhabited, "bivar"].dropna().value_counts().sort_index().items()}
        manifest["coverage_summary"][str(res)] = summary
        for d in life:
            dim_entries[d.id]["coverage"][str(res)] = _coverage(df, inhabited, d)
            dim_entries[d.id]["domains"][str(res)] = _domains(df, inhabited, d)
        manifest["spot_checks"][str(res)] = _spot_rows(df, res, spots)
        manifest["known_gaps"][str(res)] = _known_gaps(df, inhabited, life)
    manifest["dimensions"] = list(dim_entries.values())
    return manifest


def _json_default(o):
    if isinstance(o, (pd.Timestamp, dt.datetime)):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, float) and o != o:
        return None
    return str(o)


def write(settings: Settings, manifest: dict) -> Path:
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    path = settings.out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=_json_default, ensure_ascii=False), encoding="utf-8")
    return path


def load(settings: Settings) -> dict:
    path = settings.out_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing (run `export` first)")
    return json.loads(path.read_text(encoding="utf-8"))
