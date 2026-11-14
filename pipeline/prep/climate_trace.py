"""Climate TRACE emitting assets (SPEC §13.46, §15): large industrial facilities as points.

Climate TRACE publishes one download package per sector (a zip of CSVs). Each package carries
``*emissions_sources*.csv`` files with one row per asset, gas and period, so an asset appears many
times. The loader keeps assets whose subsector is on the ``subsectors:`` allow-list in
sources.yaml (point-like heavy industry: power plants, refineries, coal mines, steel, cement,
chemicals, landfills ...; area-like assets such as oil and gas fields, pipelines, farms and roads
are left out), drops rows without coordinates, keeps one row per asset and gives each a weight of
1, so a ``point_radius`` sum counts facilities within the radius. CO2e is deliberately not used:
tons of greenhouse gas measure climate impact, not local harm (Saj, 2026-11-14). CC BY 4.0.

Column names come from memory of the v4 packages and are not yet checked first-hand
(``verified: search``); the loader accepts the spellings below and stops with the columns it found
when none match.
"""

from __future__ import annotations

import fnmatch
import zipfile
from collections.abc import Iterable

import pandas as pd

MEMBER_PATTERN = "*emissions_sources*.csv"
LAT = ("lat", "latitude")
LNG = ("lon", "lng", "longitude")
SUBSECTOR = ("subsector", "original_inventory_sector", "source_type")
ASSET_ID = ("source_id", "asset_id", "id")


def _pick(columns: Iterable[str], names: tuple[str, ...], what: str, where: str) -> str:
    lower = {c.lower(): c for c in columns}
    for n in names:
        if n in lower:
            return lower[n]
    raise ValueError(f"climate_trace: {where} has no {what} column (looked for {names}; found {sorted(lower)})")


def load_frame(df: pd.DataFrame, subsectors: Iterable[str], where: str = "table") -> pd.DataFrame:
    """One row per allowed asset with coordinates: ``lat``, ``lng``, ``one`` (= 1.0)."""
    lat, lng = _pick(df.columns, LAT, "latitude", where), _pick(df.columns, LNG, "longitude", where)
    sub, aid = _pick(df.columns, SUBSECTOR, "subsector", where), _pick(df.columns, ASSET_ID, "asset id", where)
    allowed = {s.strip().lower() for s in subsectors}
    d = pd.DataFrame(
        {
            "id": df[aid].astype(str),
            "sub": df[sub].astype(str).str.strip().str.lower(),
            "lat": pd.to_numeric(df[lat], errors="coerce"),
            "lng": pd.to_numeric(df[lng], errors="coerce"),
        }
    )
    d = d[d["sub"].isin(allowed) & d["lat"].between(-90, 90) & d["lng"].between(-180, 180)]
    d = d.drop_duplicates(subset="id")
    return pd.DataFrame({"lat": d["lat"].to_numpy(), "lng": d["lng"].to_numpy(), "one": 1.0})


def load_zip(path, subsectors: Iterable[str]) -> pd.DataFrame:
    subsectors = list(subsectors)
    parts = []
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if fnmatch.fnmatch(n.rsplit("/", 1)[-1].lower(), MEMBER_PATTERN) and not n.startswith("__MACOSX/")]
        if not members:
            raise ValueError(f"climate_trace: {path.name} has no {MEMBER_PATTERN} member (found {zf.namelist()[:10]})")
        for name in members:
            with zf.open(name) as fh:
                parts.append(load_frame(pd.read_csv(fh, low_memory=False), subsectors, f"{path.name}:{name}"))
    return pd.concat(parts, ignore_index=True)


def load(settings, source, sources) -> pd.DataFrame:
    subsectors = source.extra.get("subsectors") or []
    if not subsectors:
        raise ValueError("climate_trace_assets: set `subsectors:` (the asset types to count) in sources.yaml")
    frames = [load_zip(settings.raw(source.id) / f, subsectors) for f in source.files]
    out = pd.concat(frames, ignore_index=True)
    # an asset listed in two packages is still one facility
    out = out.drop_duplicates(subset=["lat", "lng"]).reset_index(drop=True)
    print(f"prep   climate_trace_assets: {len(out)} facilities in {len(subsectors)} subsectors")
    return out
