"""Overture Maps places (SPEC §13.49): everyday amenities as points for ``amen``.

Overture's places theme is a global GeoParquet on public cloud storage (CDLA-Permissive 2.0 for
places). The whole theme is tens of millions of rows, so the raw file is a slim extract made once
on the laptop by this module's download helper:

    uv run --extra overture python -m pipeline.prep.overture_places --release <RELEASE>

It asks DuckDB for the rows whose primary category is on the ``categories:`` allow-list in
sources.yaml with confidence at or above ``min_confidence``, and writes
``data/raw/overture_places/places.parquet`` with ``lat, lng, category, confidence``. The loader
filters again (so editing the list in sources.yaml re-runs it, §13.45) and emits ``lat, lng,
one = 1.0``; ``point_radius`` with ``per_km2`` turns them into amenities per km².

Release path, the ``categories.primary`` field and the category names are from memory
(``verified: search``): newer releases may call the field ``basic_category``; the helper takes
``--category-field`` for that.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

BUCKET = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"


def load_frame(df: pd.DataFrame, categories: Iterable[str], min_confidence: float | None = None) -> pd.DataFrame:
    """One point per allowed amenity: ``lat``, ``lng``, ``one``."""
    missing = [c for c in ("lat", "lng", "category") if c not in df.columns]
    if missing:
        raise ValueError(f"overture_places: the extract lacks {missing} (found {sorted(df.columns)}); rerun the download helper")
    allowed = {c.strip().lower() for c in categories}
    keep = df["category"].astype(str).str.strip().str.lower().isin(allowed)
    if min_confidence is not None and "confidence" in df.columns:
        keep &= pd.to_numeric(df["confidence"], errors="coerce") >= float(min_confidence)
    d = df[keep]
    lat, lng = pd.to_numeric(d["lat"], errors="coerce"), pd.to_numeric(d["lng"], errors="coerce")
    ok = lat.between(-90, 90) & lng.between(-180, 180)
    return pd.DataFrame({"lat": lat[ok].to_numpy(), "lng": lng[ok].to_numpy(), "one": 1.0})


def load(settings, source, sources) -> pd.DataFrame:
    categories = source.extra.get("categories") or []
    if not categories:
        raise ValueError("overture_places: set `categories:` (the amenity types to count) in sources.yaml")
    df = pd.read_parquet(settings.raw(source.id) / source.files[0])
    out = load_frame(df, categories, source.extra.get("min_confidence"))
    print(f"prep   overture_places: {len(out)} amenities in {len(categories)} categories")
    return out


def extract_sql(release: str, categories: Iterable[str], min_confidence: float, out: Path, category_field: str = "categories.primary") -> str:
    """The DuckDB statement that writes the slim extract (pure, so it is unit-tested)."""
    cats = ", ".join("'" + c.replace("'", "''") + "'" for c in categories)
    path = BUCKET.format(release=release)
    return (
        f"COPY (SELECT ST_Y(geometry) AS lat, ST_X(geometry) AS lng, {category_field} AS category, confidence "
        f"FROM read_parquet('{path}', hive_partitioning = 1) "
        f"WHERE {category_field} IN ({cats}) AND confidence >= {float(min_confidence)}) "
        f"TO '{out.as_posix()}' (FORMAT PARQUET)"
    )


def download(release: str, category_field: str = "categories.primary") -> Path:  # pragma: no cover - needs the network
    import duckdb

    from ..config import Settings
    from ..registry import load_sources

    settings = Settings()
    src = load_sources(settings.sources_path)["overture_places"]
    out = settings.raw(src.id) / src.files[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for stmt in ("INSTALL spatial", "LOAD spatial", "INSTALL httpfs", "LOAD httpfs", "SET s3_region = 'us-west-2'"):
        con.execute(stmt)
    con.execute(extract_sql(release, src.extra["categories"], float(src.extra.get("min_confidence", 0.0)), out, category_field))
    print(f"overture_places: wrote {out}")
    return out


if __name__ == "__main__":  # pragma: no cover
    ap = argparse.ArgumentParser(description="Extract Overture everyday-amenity places to data/raw/overture_places/places.parquet")
    ap.add_argument("--release", required=True, help="Overture release, e.g. the latest listed at docs.overturemaps.org")
    ap.add_argument("--category-field", default="categories.primary", help="basic_category in newer releases")
    a = ap.parse_args()
    download(a.release, a.category_field)
