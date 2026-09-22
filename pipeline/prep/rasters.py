"""Raster builders: turn a raw source that ``rasterio`` cannot aggregate directly into one
EPSG:4326 GeoTIFF under ``data/interim/prep/<source_id>.tif`` (SPEC §20.3, ``raster_mean``).

- ``pm25_geotiff``: the ACAG SatPM2.5 NetCDF (variable ``PM25``, 0.01 degree) -> float32 GeoTIFF,
  north-up, NaN nodata, DEFLATE-compressed tiles. Written in 512-row slabs so the 2.6 GB array
  never sits in memory at once.
- ``gfed5_burned_fraction``: GFED5 monthly burned-area NetCDFs (``BA{YYYYMM}.nc`` inside
  ``BA.zip``, 0.25 degree) -> percent of each cell's area burned per year, averaged over
  2001-2020 -> float32 GeoTIFF with -9999 nodata.

Both functions are pure "input path(s) -> output path" so they can be tested on tiny synthetic
NetCDFs; :func:`pipeline.prep.load_raster` wires them to the registry and the stage cache.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from rasterio.transform import from_origin
from rasterio.windows import Window

EARTH_RADIUS_KM = 6371.0088
GFED_YEARS = (2001, 2020)  # the 0.25 degree, five-layer period of GFED5 v0.1 (1997-2000 is 1 degree)


def _latlon_names(da: xr.DataArray) -> tuple[str, str]:
    """The latitude / longitude dimension names, whatever the file calls them."""
    lat = next((d for d in da.dims if str(d).lower() in ("lat", "latitude", "y")), None)
    lon = next((d for d in da.dims if str(d).lower() in ("lon", "longitude", "x")), None)
    if lat is None or lon is None:
        raise ValueError(f"cannot find latitude/longitude dimensions in {list(da.dims)}")
    return str(lat), str(lon)


def _grid_transform(lat: np.ndarray, lon: np.ndarray, dlat: float | None = None, dlon: float | None = None):
    """Affine transform of a regular lat/lon grid (cell centres given) with north-up rows. The
    spacing comes from the file's own LAT_DELTA / LON_DELTA attributes when the caller has them;
    otherwise it is the full span over n-1 steps, not the first difference: the ACAG file stores
    float32 coordinates whose neighbour differences are off by 1e-5, which would shift the
    southern edge by 0.1 degree over 13,000 rows."""
    lat64, lon64 = lat.astype("float64"), lon.astype("float64")
    dlat = float(dlat) if dlat else float((lat64.max() - lat64.min()) / max(1, len(lat64) - 1))
    dlon = float(dlon) if dlon else float((lon64.max() - lon64.min()) / max(1, len(lon64) - 1))
    west = float(lon64.min()) - dlon / 2
    north = float(lat64.max()) + dlat / 2
    return from_origin(west, north, dlon, dlat), dlat, dlon


def _north_up(arr: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Flip rows when latitude ascends (south to north) so row 0 is the northernmost."""
    return arr[::-1] if lat[1] > lat[0] else arr


def pm25_geotiff(nc_path: Path, out: Path, variable: str = "PM25", slab_rows: int = 512) -> Path:
    """Write the annual PM2.5 field to ``out``; returns ``out``."""
    with xr.open_dataset(nc_path) as ds:
        if variable not in ds:
            raise KeyError(f"{nc_path.name}: variable {variable!r} not found; has {list(ds.data_vars)}")
        da = ds[variable].squeeze()
        lat_name, lon_name = _latlon_names(da)
        da = da.transpose(lat_name, lon_name)
        lat = da[lat_name].to_numpy()
        lon = da[lon_name].to_numpy()
        # the ACAG file states its spacing (LAT_DELTA / LON_DELTA = 0.01) as global attributes
        transform, _, _ = _grid_transform(lat, lon, ds.attrs.get("LAT_DELTA"), ds.attrs.get("LON_DELTA"))
        h, w = int(da.sizes[lat_name]), int(da.sizes[lon_name])
        ascending = lat[1] > lat[0]
        fill = da.attrs.get("_FillValue", da.encoding.get("_FillValue"))
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tif.part")
        profile = {
            "driver": "GTiff", "width": w, "height": h, "count": 1, "dtype": "float32", "crs": "EPSG:4326",
            "transform": transform, "nodata": np.nan, "tiled": True, "blockxsize": 512, "blockysize": 512,
            "compress": "deflate", "predictor": 3, "BIGTIFF": "IF_SAFER",
        }
        with rasterio.open(tmp, "w", **profile) as dst:
            for row0 in range(0, h, slab_rows):
                row1 = min(h, row0 + slab_rows)
                # output rows row0..row1 (north-up) come from input rows counted from the other end
                # when the file stores latitude ascending
                src_slice = slice(h - row1, h - row0) if ascending else slice(row0, row1)
                block = da.isel({lat_name: src_slice}).to_numpy().astype("float64")
                if ascending:
                    block = block[::-1]
                if fill is not None:
                    block = np.where(block == fill, np.nan, block)
                # the V6.GL.03 file masks water with exactly 0.0 (no _FillValue); a concentration
                # of precisely zero never occurs over land, so <= 0 is "no estimate", not clean air
                block[block <= 0] = np.nan
                dst.write(block.astype("float32"), 1, window=Window(0, row0, w, row1 - row0))
        tmp.replace(out)
    return out


def _cell_area_km2(lat: np.ndarray, dlat: float, dlon: float) -> np.ndarray:
    """Area of each 0.25 degree cell per latitude row (spherical), km2; shape (n_lat, 1)."""
    top = np.deg2rad(np.clip(lat + dlat / 2, -90, 90))
    bot = np.deg2rad(np.clip(lat - dlat / 2, -90, 90))
    area = EARTH_RADIUS_KM**2 * np.deg2rad(dlon) * np.abs(np.sin(top) - np.sin(bot))
    return area[:, None]


def _burned_variable(ds: xr.Dataset) -> str:
    """GFED5 ships Norm / Crop / Defo / Peat / Total layers; use the total."""
    for name in ds.data_vars:
        if str(name).lower() == "total":
            return str(name)
    for name in ds.data_vars:
        if "total" in str(name).lower():
            return str(name)
    if len(ds.data_vars) == 1:
        return str(next(iter(ds.data_vars)))
    raise KeyError(f"GFED5: no burned-area 'Total' variable among {list(ds.data_vars)}")


def gfed5_burned_fraction(zip_path: Path, out: Path, years: tuple[int, int] = GFED_YEARS, work_dir: Path | None = None) -> Path:
    """Mean annual burned fraction (percent of cell area per year) over ``years``; returns ``out``.

    Each monthly file holds burned area per cell; the units attribute decides whether it is an
    area (km2, divided by the cell area) or already a fraction of the cell. Anything else is
    refused with a plain message rather than guessed.
    """
    work = work_dir or out.parent / "gfed5_ba"
    work.mkdir(parents=True, exist_ok=True)
    pat = re.compile(r"BA(\d{4})(\d{2})\.nc$")
    with zipfile.ZipFile(zip_path) as z:
        members = [(int(m.group(1)), int(m.group(2)), n) for n in z.namelist() if (m := pat.search(n)) and years[0] <= int(m.group(1)) <= years[1]]
        if not members:
            raise FileNotFoundError(f"{zip_path.name}: no BA{{YYYYMM}}.nc members for {years[0]}-{years[1]}; members look like {z.namelist()[:5]}")
        members.sort()
        total: np.ndarray | None = None
        n_years = 0
        lat = lon = None
        by_year: dict[int, np.ndarray] = {}
        for year, _month, name in members:
            local = work / Path(name).name
            if not local.exists():
                with z.open(name) as src, open(local, "wb") as dst:
                    dst.write(src.read())
            with xr.open_dataset(local) as ds:
                var = _burned_variable(ds)
                da = ds[var].squeeze()
                lat_name, lon_name = _latlon_names(da)
                da = da.transpose(lat_name, lon_name)
                arr = da.to_numpy().astype("float64")
                units = str(da.attrs.get("units", "")).lower()
                if lat is None:
                    lat = da[lat_name].to_numpy()
                    lon = da[lon_name].to_numpy()
                    _, dlat, dlon = _grid_transform(lat, lon)
                    # GFED5 v0.1 files carry no `units` attribute at all (checked 2026-09-22);
                    # the record's readme documents km2 per cell per month, and monthly values
                    # above 1 rule out a fraction
                    if "km" in units or (units == "" and np.nanmax(arr) > 1.0):
                        area = _cell_area_km2(lat, dlat, dlon)
                    elif "m2" in units or "m^2" in units:
                        area = _cell_area_km2(lat, dlat, dlon) * 1e6
                    elif units in ("", "1", "fraction", "frac", "-", "unitless"):
                        area = None  # already a fraction of the cell
                    else:
                        raise ValueError(f"GFED5 {name}: burned-area units {units!r} are neither an area nor a fraction; check readme.html in {zip_path.name}")
            by_year[year] = arr if year not in by_year else by_year[year] + arr
        for _year, yearly in by_year.items():
            frac = yearly / area if area is not None else yearly
            total = frac if total is None else total + frac
            n_years += 1
    assert total is not None and lat is not None and lon is not None
    pct = 100.0 * total / n_years
    pct = np.where(np.isfinite(pct), np.clip(pct, 0, 100), -9999.0)
    pct = _north_up(pct, lat)
    transform, _, _ = _grid_transform(lat, lon)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tif.part")
    with rasterio.open(tmp, "w", driver="GTiff", width=pct.shape[1], height=pct.shape[0], count=1, dtype="float32", crs="EPSG:4326", transform=transform, nodata=-9999.0, compress="deflate") as dst:
        dst.write(pct.astype("float32"), 1)
    tmp.replace(out)
    return out
