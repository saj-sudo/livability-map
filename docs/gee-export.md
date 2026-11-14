# Google Earth Engine exports

Two recipes: Aqueduct Floods (fallback only, below) and Sentinel-5P NO2 (the `no2` layer, at the end).

# Aqueduct Floods: Google Earth Engine export (fallback only)

**Superseded 2026-09-22 (SPEC §13.19).** WRI now serves the rasters directly from
`https://aqueduct.wridata.org/AqueductFloods20/` and `pipeline/sources.yaml` fetches them as
`access: direct`. Keep this recipe only in case that mirror disappears again.

WRI removed the public S3 copies of the Aqueduct Floods hazard rasters. The dataset survives on
Google Earth Engine as `WRI/Aqueduct_Flood_Hazard_Maps/V2` (CC BY 4.0). The `fetch` stage
treats `aqueduct_floods_river` and `aqueduct_floods_coast` as `access: manual`: it checks the
files are present under `data/raw/<id>/` and prints this recipe if not.

Status: **search-only**. The image property names below are the documented ones for the V2
collection but have not been confirmed first-hand from this repo. Check the collection page
(https://developers.google.com/earth-engine/datasets/catalog/WRI_Aqueduct_Flood_Hazard_Maps_V2)
and adjust the filters, then record the result in SPEC §15.2.

## Steps (laptop, non-commercial Earth Engine account)

1. Sign up at https://earthengine.google.com (free for non-commercial use) and install the client:
   `pip install earthengine-api` then `earthengine authenticate`.
2. Run the export script below once per raster (five riverine climate models, one coastal).
   Exports land in Google Drive; download them to `data/raw/aqueduct_floods_river/` and
   `data/raw/aqueduct_floods_coast/` with the exact file names in `pipeline/sources.yaml`.
3. Run `python -m pipeline fetch --only aqueduct_floods_river --only aqueduct_floods_coast` to
   record checksums in `data/raw/CHECKSUMS`.

```python
import ee

ee.Initialize()
col = ee.ImageCollection("WRI/Aqueduct_Flood_Hazard_Maps/V2")

def export(img, name):
    task = ee.batch.Export.image.toDrive(
        image=img.toFloat(),
        description=name,
        folder="aqueduct_floods",
        fileNamePrefix=name,
        crs="EPSG:4326",
        scale=1000,                      # native is 30 arc-second (~1 km)
        region=ee.Geometry.Rectangle([-180, -60, 180, 85], None, False),
        maxPixels=1e13,
        fileFormat="GeoTIFF",
        formatOptions={"cloudOptimized": True},
    )
    task.start()
    return task

# Riverine, RCP4.5, 2050, 1-in-100 year, per climate model (VERIFY property names)
for model in ["00000NorESM1-M", "0000GFDL-ESM2M", "0000HadGEM2-ES", "00IPSL-CM5A-LR", "MIROC-ESM-CHEM"]:
    img = (col.filter(ee.Filter.eq("floodtype", "inunriver"))
              .filter(ee.Filter.eq("climatescenario", "rcp4p5"))
              .filter(ee.Filter.eq("year", 2050))
              .filter(ee.Filter.eq("returnperiod", 100))
              .filter(ee.Filter.eq("climatemodel", model))
              .first())
    export(img, f"inunriver_rcp4p5_{model}_2050_rp00100")

# Coastal, RCP4.5, 2050, 1-in-100 year, with subsidence, 50th percentile sea level
img = (col.filter(ee.Filter.eq("floodtype", "inuncoast"))
          .filter(ee.Filter.eq("climatescenario", "rcp4p5"))
          .filter(ee.Filter.eq("year", 2050))
          .filter(ee.Filter.eq("returnperiod", 100))
          .filter(ee.Filter.eq("subsidence", "wtsub"))
          .filter(ee.Filter.eq("sea_level_rise_scenario", 50))
          .first())
export(img, "inuncoast_rcp4p5_wtsub_2050_rp0100_0")
```

Depth is in metres, nodata is -9999 (0 = dry). The `hazards` stage (Session 2) takes the median
across the five riverine models before thresholding at DEPTH_MIN.

If WRI publishes a new direct download at https://www.wri.org/data/aqueduct-floods-hazard-maps,
switch both sources back to `access: direct` with that URL and delete this recipe.

---

# Sentinel-5P NO2: Google Earth Engine export (the `no2` layer, SPEC §13.49)

Unlike the floods recipe above, this one is the primary route: the annual mean is one export.
Status: **search-only** (collection and band names from memory; check the catalog page,
https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_OFFL_L3_NO2, and
record the result in SPEC §15).

1. Earth Engine account and client as in steps 1 above.
2. Run the script; the export lands in Google Drive as one GeoTIFF of about 7200 x 2900 pixels.
3. Save it as `data/raw/s5p_no2/s5p_no2_2023.tif`, then
   `uv run python -m pipeline fetch --only s5p_no2` (records the checksum) and
   `uv run python -m pipeline --res 5 dims --only no2`, then score / export / tiles.

```python
import ee

ee.Initialize()
no2 = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_NO2")
         .select("tropospheric_NO2_column_number_density")
         .filterDate("2023-01-01", "2024-01-01")
         .mean()
         .unmask(-9999)            # the pipeline reads -9999 as nodata (sources.yaml)
         .toFloat())
task = ee.batch.Export.image.toDrive(
    image=no2,
    description="s5p_no2_2023",
    folder="livability_map",
    fileNamePrefix="s5p_no2_2023",
    crs="EPSG:4326",
    crsTransform=[0.05, 0, -180, 0, -0.05, 85],   # 0.05 degree, about the TROPOMI footprint
    dimensions="7200x2900",                       # -180..180, 85..-60
    maxPixels=1e10,
    fileFormat="GeoTIFF",
)
task.start()
```

