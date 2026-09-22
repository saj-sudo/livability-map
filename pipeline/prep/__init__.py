"""``prep``: turn a raw source into the joinable layer that ``dimensions.yaml`` expects.

Format-specific parsing (ACS pipe files, OECD spreadsheets, File Geodatabases, ILOSTAT CSVs)
lives here, one module per source, so the joiners in ``pipeline/joiners/`` stay generic. Every
loader has the signature ``load(settings, source, sources) -> DataFrame | GeoDataFrame`` and
returns the columns named in the registry (for example ``emp_rate_16_29`` for ACS, ``jobs_score``
for OECD). Fixture sources are read as-is: the synthetic files already carry the final columns.

Results are cached as (Geo)Parquet under ``data/interim/prep/<source_id>.parquet`` and refreshed
when the raw files or ``PREP_VERSION`` change (SPEC §11 idempotency).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .. import stage_cache
from ..config import Settings
from ..registry import Source, load_sources

# Bump when any loader's output changes so cached layers are rebuilt.
PREP_VERSION = 4

# source id -> "module:function" (imported lazily so this package stays import-light)
LOADERS: dict[str, str] = {
    "whr_ladder": "pipeline.prep.whr:load",
    "gdl_shdi_regions": "pipeline.prep.shdi:load",
    "wb_gsap": "pipeline.prep.gsap:load",
    "ilostat_youth_unemp": "pipeline.prep.ilostat:load",
    "oecd_regional_wellbeing": "pipeline.prep.oecd:load",
    "acs_summary": "pipeline.prep.acs:load",
    "medsl_county_pres": "pipeline.prep.medsl:load",
    "epa_sld": "pipeline.prep.epa_sld:load",
    "urban_edu_districts": "pipeline.prep.urban_edu:load",
    "hrsa_ahrf": "pipeline.prep.hrsa:load",
}


def raw_inputs(settings: Settings, source: Source, sources: dict[str, Source]) -> list[Path]:
    """Every raw file a loader depends on: the source's own files plus its geometry source's."""
    paths = [settings.raw(source.id) / f for f in source.files]
    geom = source.extra.get("geometry")
    if geom:
        if geom not in sources:
            raise KeyError(f"{source.id}: geometry source {geom!r} is not in sources.yaml")
        paths += [settings.raw(geom) / f for f in sources[geom].files]
    for extra_id in source.extra.get("also_needs", []) or []:
        paths += [settings.raw(extra_id) / f for f in sources[extra_id].files]
    return paths


def _fixture_layer(settings: Settings, source: Source) -> pd.DataFrame:
    path = settings.raw(source.id) / source.files[0]
    if not path.exists():
        raise FileNotFoundError(f"{source.id}: fixture file {path} missing (run `fetch` first)")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return gpd.read_file(path)


def _missing_message(source: Source, missing: list[Path]) -> str:
    lines = [f"{source.id} is not downloaded yet: {missing[0]} is missing."]
    if source.recipe:
        lines.append("How to get it:")
        lines += ["  " + ln for ln in source.recipe.strip().splitlines()]
    else:
        lines.append(f"Run `python -m pipeline fetch --only {source.id}`.")
    return "\n".join(lines)


def _read_cached(path: Path) -> pd.DataFrame:
    try:
        return gpd.read_parquet(path)  # GeoParquet when the loader returned geometry
    except ValueError:
        return pd.read_parquet(path)


def load_layer(settings: Settings, source_id: str, sources: dict[str, Source] | None = None) -> pd.DataFrame:
    """The joinable layer for ``source_id`` (cached under data/interim/prep/)."""
    sources = sources or load_sources(settings.sources_path)
    if source_id not in sources:
        raise KeyError(f"unknown source {source_id!r} (not in {settings.sources_path.name})")
    source = sources[source_id]
    if source.access == "fixture":
        return _fixture_layer(settings, source)
    spec = LOADERS.get(source_id)
    if spec is None:
        raise KeyError(f"no prep loader for source {source_id!r}; add one to pipeline/prep/ and register it in LOADERS")
    inputs = raw_inputs(settings, source, sources)
    missing = [p for p in inputs if not p.exists()]
    if missing:
        raise FileNotFoundError(_missing_message(source, missing))
    out = settings.cache_dir / "prep" / f"{source_id}.parquet"
    params = {"source": source_id, "prep_version": PREP_VERSION}
    if stage_cache.is_fresh(out, inputs, params, settings.force):
        return _read_cached(out)
    module_name, func_name = spec.split(":")
    loader = getattr(importlib.import_module(module_name), func_name)
    df = loader(settings, source, sources)
    out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(df, gpd.GeoDataFrame):
        df.to_parquet(out, index=False)
    else:
        pd.DataFrame(df).to_parquet(out, index=False)
    stage_cache.record(out, inputs, params, {"rows": int(len(df)), "columns": list(map(str, df.columns))})
    print(f"prep   {source_id}: {len(df)} rows -> {out.relative_to(settings.data_dir)}")
    return df
