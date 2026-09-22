"""Build web/public/gazetteer.json, the bundled place index for search (SPEC §10; invariant 7:
no request leaves the origin, so names ship with the site).

Sources (both registered in pipeline/sources.yaml):
  natural_earth_places  Natural Earth 1:10m populated places (public domain): cities with a
                        population estimate; kept when POP_MAX >= MIN_CITY_POP or the place is a
                        national capital.
  geoboundaries_adm1    geoBoundaries CGAZ ADM1 (CC BY 4.0): first-level regions, one point each
                        (representative point of the largest part), names repaired with
                        pipeline.prep.util.fix_mojibake.

Run from the repository root after `python -m pipeline fetch --only natural_earth_places`:

    python web/scripts/build_gazetteer.py [--raw data/raw] [--adm1 <path to gpkg>] [--out web/public/gazetteer.json]

Output rows are [name, key, kind, iso2, lat, lng, pop] with kind "c" (city) or "r" (region);
`key` is the folded search key (lowercase ASCII, punctuation collapsed) computed the same way
as web/src/lib/search.ts foldKey so the browser never has to fold the whole list.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.prep.util import fix_mojibake  # noqa: E402

MIN_CITY_POP = 50_000
NE_ZIP = "ne_10m_populated_places.zip"
ADM1_GPKG = "geoBoundariesCGAZ_ADM1.gpkg"


def fold_key(text: str) -> str:
    """Mirror of foldKey in web/src/lib/search.ts."""
    s = unicodedata.normalize("NFKD", fix_mojibake(str(text))).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def iso3_to_iso2(codes: pd.Series) -> pd.Series:
    """ISO3 -> ISO2 the way the admin stage does it (pycountry via pipeline.prep.util)."""
    from pipeline.prep.util import iso3_to_iso2 as convert

    return convert(codes, {}).fillna("")


def cities(raw: Path) -> list[list]:
    zpath = raw / "natural_earth_places" / NE_ZIP
    if not zpath.exists():
        sys.exit(f"missing {zpath}: run `python -m pipeline fetch --only natural_earth_places` first")
    with zipfile.ZipFile(zpath) as z:
        shp = next(n for n in z.namelist() if n.endswith(".shp"))
    gdf = gpd.read_file(f"zip://{zpath}!{shp}", engine="pyogrio")
    gdf = gdf.to_crs(4326) if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf
    pop = pd.to_numeric(gdf["POP_MAX"], errors="coerce").fillna(0)
    capital = gdf["FEATURECLA"].astype(str).str.contains("capital", case=False, na=False)
    keep = gdf[(pop >= MIN_CITY_POP) | capital].copy()
    keep["pop"] = pop[keep.index].astype(int)
    rows = []
    for _, r in keep.iterrows():
        name = fix_mojibake(str(r["NAME"]))
        iso2 = str(r.get("ISO_A2", "") or "")
        if iso2 in ("-99", "-1", "nan"):
            iso2 = ""
        rows.append([name, fold_key(name), "c", iso2, round(float(r.geometry.y), 3), round(float(r.geometry.x), 3), int(r["pop"])])
    return rows


def regions(adm1: Path) -> list[list]:
    if not adm1.exists():
        sys.exit(f"missing {adm1}: run `python -m pipeline fetch --only geoboundaries_adm1` first")
    gdf = gpd.read_file(adm1, engine="pyogrio", columns=["shapeName", "shapeGroup"])
    pts = gdf.geometry.representative_point()
    iso2 = iso3_to_iso2(gdf["shapeGroup"])
    rows = []
    for name, code, pt in zip(gdf["shapeName"], iso2, pts, strict=True):
        name = fix_mojibake(str(name)).strip()
        if not name or name.lower() in ("none", "nan"):
            continue
        rows.append([name, fold_key(name), "r", str(code or ""), round(float(pt.y), 3), round(float(pt.x), 3), None])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(ROOT / "data" / "raw"), help="data/raw directory holding the fetched sources")
    ap.add_argument("--adm1", default=None, help="path to geoBoundariesCGAZ_ADM1.gpkg (default: <raw>/geoboundaries_adm1/...)")
    ap.add_argument("--out", default=str(ROOT / "web" / "public" / "gazetteer.json"))
    a = ap.parse_args()
    raw = Path(a.raw)
    adm1 = Path(a.adm1) if a.adm1 else raw / "geoboundaries_adm1" / ADM1_GPKG

    rows = cities(raw) + regions(adm1)
    # drop exact duplicates (same name, kind, country, rounded point)
    seen: set[tuple] = set()
    uniq = []
    for r in rows:
        k = (r[1], r[2], r[3], r[4], r[5])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    # the browser recomputes the key from the name when it is empty, so only unusual keys ship
    for r in uniq:
        if r[1] == r[0].lower():
            r[1] = ""
    out = {"v": 1, "built": date.today().isoformat(), "sources": ["natural_earth_places", "geoboundaries_adm1"], "places": uniq}
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    Path(a.out).write_text(text, encoding="utf-8")
    n_c = sum(1 for r in uniq if r[2] == "c")
    n_r = len(uniq) - n_c
    print(f"gazetteer: {n_c} cities (POP_MAX >= {MIN_CITY_POP:,} or capital) + {n_r} regions -> {a.out} ({len(text.encode('utf-8')) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
