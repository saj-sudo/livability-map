"""Generate the synthetic fixture world (SPEC §11.1) into ``pipeline/fixtures/data/``.

A 4 x 4 degree region (lng 10..14, lat 40..44) with:
- land polygon with a coastal bite in the south-east and one small island
- two countries (user-assigned ISO3 XKA, XKB) and five admin1 regions
- a 0.01 degree population raster with four towns and an empty desert
- a 0.25 degree heat NetCDF (hd35), 0.01 degree riverine and coastal flood GeoTIFFs,
  water-stress polygons (bau50_ws_x_c incl. -1)
- tabular wellbeing (SHDI with two missing regions, WHR for both countries)
- global life-dimension stand-ins: GSAP regions (all five admin1), OECD TL2 (XKA only), ILOSTAT
- US-like detail layers over XKB: tracts (ACS-like fields), counties (margin, physicians,
  2-bedroom rent, metro price parity), block groups (EPA SLD-like), school districts, transit
  stops (for joiner and dims tests)
- cost-of-living stand-ins: states (BEA-like price parity for two of the three XKB regions, so
  the third falls through to the national fallback), ICP-like (XA only) and WDI-like (both)
  national price levels

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
from rasterio import features
from rasterio.transform import from_origin
from shapely.geometry import Point, Polygon, box

from ..sanity import Spot

VERSION = 6  # bump when the world changes; ensure() regenerates on mismatch
ISO_OVERRIDES = {"XKA": "XA", "XKB": "XB"}
BBOX = (10.0, 40.0, 14.0, 44.0)
PX = 0.01  # degrees per pixel for the 1 km-ish rasters
NODATA_POP = -200.0
NODATA_FLOOD = -9999.0
NODATA_CARE = -9999.0  # travel-time raster nodata (as the real MAP file)

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
    drr = [np.nan, 0.0, 1.0, 3.0, 4.0, 2.0]  # baseline drought risk 0-4; desert = no data (real file: -9999)
    return gpd.GeoDataFrame(
        {"bau50_ws_x_c": [p[1] for p in polys], "bau50_ws_x_r": [p[2] for p in polys], "drr_cat": drr, "pfaf_id": list(range(100001, 100001 + len(polys)))},
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
            # racial shares (ACS B03002-like) that always sum to exactly 100
            pct_black = round(10 + 45 * max(0.0, 1 - abs(cy - 41.0) / 0.6), 1)
            pct_hisp = round(5 + 15 * near_cedar, 1)
            pct_asian = round(3 + 7 * near_cedar, 1)
            pct_other = 4.0
            pct_white = round(100 - pct_black - pct_hisp - pct_asian - pct_other, 1)
            geoid = f"XKB{i:02d}{j:02d}"
            cells.append(
                {
                    "GEOID": geoid,
                    "GEOIDFQ": f"1400000US{geoid}",
                    "pop_total": float(round(200 + 20000 * near_cedar)),
                    "households": float(round(80 + 8000 * near_cedar)),
                    "emp_rate_16_29": float(round(0.55 + 0.35 * near_cedar, 3)),
                    "pop_16_29": float(round(40 + 5000 * near_cedar)),
                    "ss_couples_per_1k": float(round(2 + 20 * near_cedar, 2)),
                    "pct_white": float(pct_white),
                    "pct_black": float(pct_black),
                    "pct_hisp": float(pct_hisp),
                    "pct_asian": float(pct_asian),
                    "pct_other": float(pct_other),
                    "income_entropy": float(round(0.6 + 0.35 * near_cedar, 3)),
                    "gini": float(round(0.4 + 0.1 * near_cedar, 3)),
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
            "physicians_per_10k": [35.0, 18.0, 5.0, 12.0],
            # HUD-like 2-bedroom rent (USD/month) for every county ...
            "fmr_2br": [1450.0, 980.0, 700.0, 1120.0],
            # ... but a BEA-like metro price parity (US = 100) only for the Cedar metro: the
            # other counties are NULL so the cost dimension falls through to the state layer
            "rpp_all": [108.5, np.nan, np.nan, np.nan],
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


def us_like_detail_layers(land):
    """EPA SLD-like block groups (0.1 degree) and school districts (0.5 degree) over XKB."""
    bgs = []
    for i, x in enumerate(np.arange(12.6, 14.0, 0.1)):
        for j, y in enumerate(np.arange(40.0, 44.0, 0.1)):
            g = box(x, y, x + 0.1, y + 0.1).intersection(land)
            if g.is_empty:
                continue
            near_cedar = np.exp(-((x + 0.05 - 13.0) ** 2 + (y + 0.05 - 42.5) ** 2) / (2 * 0.3**2))
            bgs.append(
                {
                    "GEOID20": f"XKB{i:03d}{j:03d}",
                    "D4C": -99999.0 if (i, j) == (0, 0) else float(round(60 * near_cedar, 2)),  # SLD sentinel once
                    "NatWalkInd": float(round(4 + 12 * near_cedar, 2)),
                    "TotPop": float(round(50 + 5000 * near_cedar)),
                    "geometry": g,
                }
            )
    sld = gpd.GeoDataFrame(bgs, geometry="geometry", crs=4326)
    districts = []
    k = 0
    for x in np.arange(12.0, 14.0, 0.5):
        for y in np.arange(40.0, 44.0, 0.5):
            g = box(x, y, x + 0.5, y + 0.5).intersection(land)
            if g.is_empty:
                continue
            k += 1
            near_cedar = np.exp(-((x + 0.25 - 13.0) ** 2 + (y + 0.25 - 42.5) ** 2) / (2 * 0.5**2))
            districts.append(
                {
                    "LEAID": f"XKB{k:04d}",
                    "grad_rate_midpt": float(round(70 + 25 * near_cedar, 1)),
                    "cohort_num": float(round(50 + 400 * near_cedar)),
                    "geometry": g,
                }
            )
    return sld, gpd.GeoDataFrame(districts, geometry="geometry", crs=4326)


def global_life_layers(adm1: gpd.GeoDataFrame):
    """GSAP-like poverty regions (all five admin1), OECD TL2-like regions (XKA only), ILOSTAT-like table."""
    gsap = adm1[["shapeGroup", "shapeName", "geometry"]].copy()
    gsap["geo_code"] = [f"{g}_2023_ADM1_{i + 1}" for i, g in enumerate(gsap["shapeGroup"])]
    gsap["nonpoor_share"] = [0.95, 0.85, 0.70, 0.55, 0.40]
    gsap = gpd.GeoDataFrame(gsap[["geo_code", "nonpoor_share", "geometry"]], geometry="geometry", crs=4326)
    xka = adm1[adm1["shapeGroup"] == "XKA"].copy()
    oecd = gpd.GeoDataFrame(
        {
            "Code": ["XA1", "XA2"],
            "Region": list(xka["shapeName"]),
            "jobs_score": [8.0, 6.5],
            "housing_burden": [3.0, 4.5],
            "health_score": [7.5, 6.0],
        },
        geometry=list(xka.geometry),
        crs=4326,
    )
    ilostat = pd.DataFrame(
        {"iso_a2": ["XA", "XB"], "iso_a3": ["XKA", "XKB"], "youth_employment_rate": [85.0, 78.0], "year": [2024, 2024]}
    )
    return gsap, oecd, ilostat


def cost_layers(adm1: gpd.GeoDataFrame):
    """Stand-ins for the cost-of-living sources (SPEC §20.6 cost).

    - ``states``: BEA-like state price parities (US = 100) as polygons keyed like the Census
      state file (``GEOID``). Only B-North and B-Mid are priced; B-South is left out so one XKB
      region exercises the national fallback in the fixture world.
    - ``icp``: ICP-like household price level (World = 100) for XA only.
    - ``gdp``: WDI-like GDP price level already rescaled to the world base, for both countries,
      so it is the last-resort fill for XB's B-South (and never wins for XA, where ICP comes first).
    """
    xkb = adm1[adm1["shapeGroup"] == "XKB"].set_index("shapeName")
    states = gpd.GeoDataFrame(
        {"GEOID": ["XB1", "XB2"], "name": ["B-North", "B-Mid"], "rpp_all": [97.0, 104.0], "year": [2024, 2024]},
        geometry=[xkb.loc["B-North", "geometry"], xkb.loc["B-Mid", "geometry"]],
        crs=4326,
    )
    icp = pd.DataFrame({"iso_a3": ["XKA"], "iso_a2": ["XA"], "pli_household": [88.0], "year": [2021]})
    gdp = pd.DataFrame({"iso_a3": ["XKA", "XKB"], "iso_a2": ["XA", "XB"], "pli_gdp": [85.0, 121.0], "pli_ratio_us": [0.85, 1.21], "year": [2024, 2024]})
    return states, icp, gdp


def _content_digest(path: Path) -> str:
    """sha256 of file bytes, or of WKB + attributes for vector files (GeoPackage is not byte-stable)."""
    if path.suffix in (".gpkg", ".fgb", ".shp"):
        gdf = gpd.read_file(path)
        h = hashlib.sha256()
        h.update(gdf.drop(columns="geometry").to_csv(index=False).encode())
        h.update(b"".join(gdf.geometry.to_wkb()))
        return h.hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_tif_u8(path: Path, arr: np.ndarray, transform, nodata: int = 255) -> None:
    """uint8 GeoTIFF (the tree-cover mosaic is uint8 percent with 255 nodata)."""
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="uint8", crs="EPSG:4326", transform=transform, nodata=nodata, compress="deflate", tiled=True, blockxsize=256, blockysize=256) as dst:
        dst.write(arr.astype("uint8"), 1)


def _town_distance(LNG, LAT):
    """Distance in degrees from each pixel to the nearest town centre."""
    d = np.full(LNG.shape, np.inf)
    for lng, lat, _pop, _sigma in TOWNS.values():
        d = np.minimum(d, np.hypot(LNG - lng, LAT - lat))
    return d


def extras_rasters(LNG, LAT, land: np.ndarray):
    """Stand-ins for the hex-level raster extras (SPEC §20.6): travel time to healthcare (minutes,
    grows with the distance to the nearest town), PM2.5 (worst near Cedar, cleanest in the far
    north-west, negative sentinel off land like the real ACAG file) and burned area (percent of
    area per year on a coarse 0.25 degree grid: 6 around the desert edge, 0.5 elsewhere)."""
    dist = _town_distance(LNG, LAT)
    care = np.where(land, 8.0 + 220.0 * dist, NODATA_CARE)
    near_cedar = np.exp(-((LNG - 13.0) ** 2 + (LAT - 42.5) ** 2) / (2 * 0.6**2))
    pm25 = np.where(land, 4.0 + 30.0 * near_cedar + 2.0 * (44.0 - LAT), -999.0)
    # 0.25 degree grid over the same bbox (16 x 16 cells)
    minlng, minlat, maxlng, maxlat = BBOX
    lng_c = np.arange(minlng + 0.125, maxlng, 0.25)
    lat_c = np.arange(maxlat - 0.125, minlat, -0.25)
    CLNG, CLAT = np.meshgrid(lng_c, lat_c)
    fire = np.full(CLNG.shape, 0.5)
    fire[(CLNG > 12.0) & (CLNG < 13.5) & (CLAT > 40.0) & (CLAT < 41.5)] = 6.0  # the dry south-east
    fire[(CLNG > 10.0) & (CLNG < 11.5) & (CLAT > 42.5)] = 0.0  # the wet north-west around Alder never burns
    coarse_transform = from_origin(minlng, maxlat, 0.25, 0.25)
    return care, pm25, fire, coarse_transform


def tree_raster(land_geom):
    """Tree-cover fraction at 0.002 degree (five times finer than the other fixture rasters) so
    `decimate: 10` is exercised: 85 percent in the north-west quadrant, 12 elsewhere, 0 in the
    desert, 255 (nodata) off land."""
    minlng, minlat, maxlng, maxlat = BBOX
    px = 0.002
    lng = np.arange(minlng + px / 2, maxlng, px)
    lat = np.arange(maxlat - px / 2, minlat, -px)
    LNG, LAT = np.meshgrid(lng, lat)
    land = features.rasterize([(land_geom, 1)], out_shape=LNG.shape, transform=from_origin(minlng, maxlat, px, px), fill=0, dtype="uint8").astype(bool)
    trees = np.where((LNG < 12.0) & (LAT > 42.0), 85, 12).astype("uint8")
    trees[(LNG > 12.5) & (LNG < 13.5) & (LAT > 40.0) & (LAT < 41.0)] = 0
    trees[~land] = 255
    return trees, from_origin(minlng, maxlat, px, px)


def ookla_points():
    """Speed-tile centroids: fixed broadband around Alder, Birch and Cedar (no fixed tiles at
    Dune), mobile tiles at Dune and Cedar; `point_mean` must weight by tests and the mobile
    joiner must only fill Dune (first hit wins)."""
    rng = np.random.default_rng(7)
    rows = []
    for name, (lng, lat, _pop, _sigma) in TOWNS.items():
        if name == "Dune":
            continue
        mbps = {"Alder": 210.0, "Birch": 75.0, "Cedar": 320.0}[name]
        for _ in range(12):
            rows.append({"lat": lat + rng.normal(0, 0.03), "lng": lng + rng.normal(0, 0.03), "d_mbps": mbps * rng.uniform(0.8, 1.2), "tests": int(rng.integers(5, 60))})
    fixed = pd.DataFrame(rows)
    mob = []
    for name in ("Dune", "Cedar"):
        lng, lat, _pop, _sigma = TOWNS[name]
        for _ in range(8):
            mob.append({"lat": lat + rng.normal(0, 0.03), "lng": lng + rng.normal(0, 0.03), "d_mbps": 42.0 * rng.uniform(0.8, 1.2), "tests": int(rng.integers(3, 30))})
    return fixed, pd.DataFrame(mob)


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
    sld, districts = us_like_detail_layers(land_gdf.geometry.iloc[0])
    sld.to_file(out / "sld.gpkg", driver="GPKG")
    districts.to_file(out / "districts.gpkg", driver="GPKG")
    gsap, oecd, ilostat = global_life_layers(adm1)
    gsap.to_file(out / "gsap_regions.gpkg", driver="GPKG")
    oecd.to_file(out / "oecd_tl2.gpkg", driver="GPKG")
    ilostat.to_csv(out / "ilostat.csv", index=False)
    states, icp, gdp = cost_layers(adm1)
    states.to_file(out / "states.gpkg", driver="GPKG")
    icp.to_csv(out / "icp.csv", index=False)
    gdp.to_csv(out / "gdp_pli.csv", index=False)
    care, pm25, fire, coarse = extras_rasters(LNG, LAT, land)
    _write_tif(out / "care.tif", care, transform, NODATA_CARE)
    _write_tif(out / "pm25.tif", pm25, transform, np.nan)
    _write_tif(out / "fire.tif", fire, coarse, -9999.0)
    trees, tree_transform = tree_raster(land_gdf.geometry.iloc[0])
    _write_tif_u8(out / "trees.tif", trees, tree_transform, 255)
    fixed, mobile = ookla_points()
    fixed.to_csv(out / "ookla_fixed.csv", index=False)
    mobile.to_csv(out / "ookla_mobile.csv", index=False)

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
