"""Generate the synthetic fixture world (SPEC §11.1) into ``pipeline/fixtures/data/``.

A 4 x 4 degree region (lng 10..14, lat 40..44) with:
- land polygon with a coastal bite in the south-east and one small island
- two countries (user-assigned ISO3 XKA, XKB) and five admin1 regions
- a 0.01 degree population raster with four towns and an empty desert
- a 0.25 degree heat NetCDF (hd35), 0.01 degree riverine and coastal flood GeoTIFFs,
  water-stress polygons (bau50_ws_x_c incl. -1)
- tabular wellbeing (SHDI with two missing regions, WHR for both countries)
- US-like detail layers: tracts, counties, transit stops (for joiner tests)

Everything is analytic or seeded, so regeneration is content-deterministic: rasters, CSV and
NetCDF are byte-identical; GeoPackage files embed a write timestamp, so their digest in
``fixtures.json`` is taken over geometry (WKB) and attributes instead of bytes.
Run ``python -m pipeline.fixtures.make_fixtures`` or rely on ``--fixtures`` to generate lazily.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.transform import from_origin
from shapely.geometry import Point, Polygon, box

from ..sanity import Spot

VERSION = 3  # bump when the world changes; ensure() regenerates on mismatch
ISO_OVERRIDES = {"XKA": "XA", "XKB": "XB"}
BBOX = (10.0, 40.0, 14.0, 44.0)
PX = 0.01  # degrees per pixel for the 1 km-ish rasters
NODATA_POP = -200.0
NODATA_FLOOD = -9999.0

TOWNS = {  # name: (lng, lat, peak persons/pixel, sigma degrees)
    "Alder": (11.0, 43.0, 3000.0, 0.05),
    "Birch": (11.5, 41.0, 1500.0, 0.04),
    "Cedar": (13.0, 42.5, 4000.0, 0.06),
    "Dune": (13.6, 43.6, 300.0, 0.03),
}
DESERT = box(12.0, 40.0, 13.0, 41.5)  # zero population -> uninhabited hexes
COAST_WEDGE = Polygon([(12.6, 40.0), (14.0, 40.0), (14.0, 41.6)])  # ocean
ISLAND = Point(13.5, 40.45).buffer(0.18)

SPOT_CHECKS = [
    Spot("Alder (XKA)", 43.0, 11.0, "inhabited, XKA / A-North"),
    Spot("Cedar (XKB)", 42.5, 13.0, "inhabited, XKB / B-Mid"),
    Spot("Desert (XKB)", 40.7, 12.5, "uninhabited, XKB / B-South"),
    Spot("Island", 40.45, 13.5, "land hex if a cell centre falls on it, else absent"),
    Spot("Ocean", 40.3, 13.8, "not a land hex"),
]


def land_geometry() -> gpd.GeoDataFrame:
    land = box(*BBOX).difference(COAST_WEDGE).union(ISLAND)
    return gpd.GeoDataFrame({"featurecla": ["Land"]}, geometry=[land], crs=4326)


def admin_geometries() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    land = land_geometry().geometry.iloc[0]
    a = box(10.0, 40.0, 12.0, 44.0).intersection(land)
    b = box(12.0, 40.0, 14.0, 44.0).intersection(land)
    adm0 = gpd.GeoDataFrame(
        {"shapeGroup": ["XKA", "XKB"], "shapeName": ["Alderland", "Cedaria"], "shapeType": ["ADM0", "ADM0"]},
        geometry=[a, b],
        crs=4326,
    )
    regions = [
        ("XKA", "A-North", box(10.0, 42.0, 12.0, 44.0)),
        ("XKA", "A-South", box(10.0, 40.0, 12.0, 42.0)),
        ("XKB", "B-North", box(12.0, 43.0, 14.0, 44.0)),
        ("XKB", "B-Mid", box(12.0, 41.5, 14.0, 43.0)),
        ("XKB", "B-South", box(12.0, 40.0, 14.0, 41.5)),
    ]
    adm1 = gpd.GeoDataFrame(
        {
            "shapeGroup": [r[0] for r in regions],
            "shapeName": [r[1] for r in regions],
            "shapeID": [f"{r[0]}-ADM1-{i + 1}" for i, r in enumerate(regions)],
            "shapeType": ["ADM1"] * len(regions),
        },
        geometry=[r[2].intersection(land) for r in regions],
        crs=4326,
    )
    return adm0, adm1


def _grid():
    minlng, minlat, maxlng, maxlat = BBOX
    ncol = int(round((maxlng - minlng) / PX))
    nrow = int(round((maxlat - minlat) / PX))
    lng = minlng + (np.arange(ncol) + 0.5) * PX
    lat = maxlat - (np.arange(nrow) + 0.5) * PX
    LNG, LAT = np.meshgrid(lng, lat)
    transform = from_origin(minlng, maxlat, PX, PX)
    return LNG, LAT, transform


def _write_tif(path: Path, arr: np.ndarray, transform, nodata: float) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
        compress="deflate",
        tiled=True,
        blockxsize=128,
        blockysize=128,
    ) as dst:
        dst.write(arr.astype("float32"), 1)


def _land_mask(LNG, LAT) -> np.ndarray:
    land = land_geometry().geometry.iloc[0]
    # vectorized containment via shapely 2
    import shapely

    pts = shapely.points(LNG.ravel(), LAT.ravel())
    return shapely.contains(land, pts).reshape(LNG.shape)


def population_raster(LNG, LAT, land: np.ndarray) -> np.ndarray:
    pop = np.full(LNG.shape, 1.5, dtype="float64")
    for _, (x, y, peak, sigma) in TOWNS.items():
        pop += peak * np.exp(-((LNG - x) ** 2 + (LAT - y) ** 2) / (2 * sigma**2))
    import shapely

    desert = shapely.contains(DESERT, shapely.points(LNG.ravel(), LAT.ravel())).reshape(LNG.shape)
    pop[desert] = 0.0
    pop[~land] = 0.0
    # nodata outside a margin to exercise the nodata path (bottom-right ocean corner)
    pop[(LNG > 13.7) & (LAT < 40.2)] = NODATA_POP
    return pop


def river_raster(LNG, LAT, land: np.ndarray) -> np.ndarray:
    # river from (10.2, 43.8) to (13.0, 40.2): distance from a line segment
    x0, y0, x1, y1 = 10.2, 43.8, 13.0, 40.2
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((LNG - x0) * dx + (LAT - y0) * dy) / (dx * dx + dy * dy), 0, 1)
    d = np.hypot(LNG - (x0 + t * dx), LAT - (y0 + t * dy))
    depth = np.where(d < 0.08, 2.0 * (1 - d / 0.08), 0.0)
    # floodplain around Cedar
    depth += np.where(np.hypot(LNG - 13.0, LAT - 42.5) < 0.12, 0.4, 0.0)
    depth[~land] = NODATA_FLOOD
    return depth


def coast_raster(LNG, LAT, land: np.ndarray) -> np.ndarray:
    # distance to the coast line of the wedge (from (12.6,40) to (14,41.6))
    x0, y0, x1, y1 = 12.6, 40.0, 14.0, 41.6
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((LNG - x0) * dx + (LAT - y0) * dy) / (dx * dx + dy * dy), 0, 1)
    d = np.hypot(LNG - (x0 + t * dx), LAT - (y0 + t * dy))
    depth = np.where(d < 0.15, 1.0 * (1 - d / 0.15), 0.0)
    depth[~land] = NODATA_FLOOD
    return depth


def heat_dataset() -> xr.Dataset:
    lat = np.arange(44.125, 39.75, -0.25)
    lon = np.arange(9.875, 14.25, 0.25)
    LON, LAT = np.meshgrid(lon, lat)
    hd35 = 5.0 + 40.0 * (44.0 - LAT) / 4.0 + 3.0 * (LON - 10.0)
    return xr.Dataset(
        {"hd35": (("lat", "lon"), hd35.astype("float32"), {"units": "days", "long_name": "Number of hot days (Tmax > 35C)"})},
        coords={"lat": lat, "lon": lon},
        attrs={"title": "fixture hd35 climatology, synthetic"},
    )


def water_stress() -> gpd.GeoDataFrame:
    land = land_geometry().geometry.iloc[0]
    polys = [
        (DESERT, -1, np.nan),
        (box(10.0, 40.0, 12.0, 42.0), 0, 0.05),
        (box(10.0, 42.0, 12.0, 44.0), 1, 0.15),
        (box(12.0, 41.5, 14.0, 43.0).difference(DESERT), 3, 0.55),
        (box(12.0, 43.0, 14.0, 44.0), 4, 0.9),
        (box(12.0, 40.0, 14.0, 41.5).difference(DESERT), 2, 0.3),
    ]
    return gpd.GeoDataFrame(
        {"bau50_ws_x_c": [p[1] for p in polys], "bau50_ws_x_r": [p[2] for p in polys], "pfaf_id": list(range(100001, 100001 + len(polys)))},
        geometry=[p[0].intersection(land) for p in polys],
        crs=4326,
    )


def tabular(adm1: gpd.GeoDataFrame):
    shdi = pd.DataFrame(
        {
            "GDLCODE": ["XKAr101", "XKAr102", "XKBr101"],
            "region": ["A-North", "A-South", "B-North"],
            "iso_code": ["XKA", "XKA", "XKB"],
            "year": [2023, 2023, 2023],
            "shdi": [0.82, 0.75, 0.60],
        }
    )
    regions = adm1[adm1["shapeName"].isin(shdi["region"])].copy()
    regions["GDLCODE"] = regions["shapeName"].map(dict(zip(shdi["region"], shdi["GDLCODE"], strict=True)))
    regions = regions.merge(shdi[["GDLCODE", "shdi"]], on="GDLCODE")[["GDLCODE", "shdi", "geometry"]]
    whr = pd.DataFrame({"iso_a2": ["XA", "XB"], "country": ["Alderland", "Cedaria"], "ladder": [6.9, 5.1]})
    return shdi, gpd.GeoDataFrame(regions, geometry="geometry", crs=4326), whr


def us_like_layers(land, rng: np.random.Generator):
    # tracts: 0.2 degree grid over XKB with plausible fields
    cells = []
    for i, x in enumerate(np.arange(12.0, 14.0, 0.2)):
        for j, y in enumerate(np.arange(40.0, 44.0, 0.2)):
            g = box(x, y, x + 0.2, y + 0.2).intersection(land)
            if g.is_empty:
                continue
            cx, cy = x + 0.1, y + 0.1
            near_cedar = np.exp(-((cx - 13.0) ** 2 + (cy - 42.5) ** 2) / (2 * 0.3**2))
            cells.append(
                {
                    "GEOID": f"XKB{i:02d}{j:02d}",
                    "pop_total": float(round(200 + 20000 * near_cedar)),
                    "households": float(round(80 + 8000 * near_cedar)),
                    "emp_rate_16_29": float(round(0.55 + 0.35 * near_cedar, 3)),
                    "pop_16_29": float(round(40 + 5000 * near_cedar)),
                    "pct_black": float(round(10 + 60 * max(0.0, 1 - abs(cy - 41.0) / 0.6), 1)),
                    "rent_share_income": float(round(0.22 + 0.2 * near_cedar, 3)),
                    "renter_households": float(round(30 + 5000 * near_cedar)),
                    "geometry": g,
                }
            )
    tracts = gpd.GeoDataFrame(cells, geometry="geometry", crs=4326)
    counties = gpd.GeoDataFrame(
        {
            "GEOID": ["XKB001", "XKB002", "XKB003", "XKB004"],
            "name": ["Cedar Co", "North Co", "Desert Co", "Coast Co"],
            "margin_2024": [35.0, -20.0, -60.0, 5.0],
        },
        geometry=[
            box(12.0, 41.5, 14.0, 43.0).intersection(land),
            box(12.0, 43.0, 14.0, 44.0).intersection(land),
            DESERT.intersection(land),
            box(12.0, 40.0, 14.0, 41.5).difference(DESERT).intersection(land),
        ],
        crs=4326,
    )
    stops = []
    for name, n in (("Cedar", 60), ("Alder", 20)):
        x, y, _, sigma = TOWNS[name]
        pts = rng.normal(loc=(x, y), scale=sigma * 1.5, size=(n, 2))
        stops += [Point(float(px), float(py)) for px, py in pts]
    transit = gpd.GeoDataFrame({"stop_id": [f"S{i:03d}" for i in range(len(stops))]}, geometry=stops, crs=4326)
    return tracts, counties, transit


def _content_digest(path: Path) -> str:
    """sha256 of file bytes, or of WKB + attributes for vector files (GeoPackage is not byte-stable)."""
    if path.suffix in (".gpkg", ".fgb", ".shp"):
        gdf = gpd.read_file(path)
        h = hashlib.sha256()
        h.update(gdf.drop(columns="geometry").to_csv(index=False).encode())
        h.update(b"".join(gdf.geometry.to_wkb()))
        return h.hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out: Path) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    land_gdf = land_geometry()
    land_gdf.to_file(out / "land.gpkg", driver="GPKG")
    adm0, adm1 = admin_geometries()
    adm0.to_file(out / "adm0.gpkg", driver="GPKG")
    adm1.to_file(out / "adm1.gpkg", driver="GPKG")

    LNG, LAT, transform = _grid()
    land = _land_mask(LNG, LAT)
    _write_tif(out / "pop.tif", population_raster(LNG, LAT, land), transform, NODATA_POP)
    _write_tif(out / "inunriver.tif", river_raster(LNG, LAT, land), transform, NODATA_FLOOD)
    _write_tif(out / "inuncoast.tif", coast_raster(LNG, LAT, land), transform, NODATA_FLOOD)
    heat_dataset().to_netcdf(out / "heat.nc", engine="netcdf4")
    water_stress().to_file(out / "wstress.gpkg", driver="GPKG")

    shdi, regions, whr = tabular(adm1)
    shdi.to_csv(out / "shdi.csv", index=False)
    regions.to_file(out / "shdi_regions.gpkg", driver="GPKG")
    whr.to_csv(out / "whr.csv", index=False)

    tracts, counties, transit = us_like_layers(land_gdf.geometry.iloc[0], rng)
    tracts.to_file(out / "tracts.gpkg", driver="GPKG")
    counties.to_file(out / "counties.gpkg", driver="GPKG")
    transit.to_file(out / "transit_stops.gpkg", driver="GPKG")

    digests = {p.name: _content_digest(p) for p in sorted(out.iterdir()) if p.suffix != ".json"}
    (out / "fixtures.json").write_text(json.dumps({"version": VERSION, "files": digests}, indent=2), encoding="utf-8")
    return digests


def ensure(out: Path) -> Path:
    marker = out / "fixtures.json"
    if marker.exists():
        try:
            if json.loads(marker.read_text(encoding="utf-8")).get("version") == VERSION:
                return out
        except json.JSONDecodeError:
            pass
    print(f"fixtures: generating synthetic world v{VERSION} in {out}")
    build(out)
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
    for name, digest in build(target).items():
        print(f"{digest[:12]}  {name}")
