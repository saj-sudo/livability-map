# SPEC.md - livability-map (working title: Global Climate Livability Map)

Version 0.3 | 2026-09-22 | Owner: Saj | Status: Sessions 1-7 built; Cloudflare publish/deploy waits on credentials (§13.24)

Sections are numbered so build prompts can cite them. v0.1 (2026-09-08) was the pre-build
draft; v0.2 records the Session 0 decisions (§13), the verification log (§15), and the new
life-dimensions design (§20). v0.3 (2026-09-22) records the first-hand verification of every
source, the decisions taken while building Sessions 2-7 (§13.18-26) and the res-4 global run (§11).

## 0. How to use this spec with Claude Code

1. This file lives at the repo root as `SPEC.md`. `CLAUDE.md` is generated with `/init`, never
   hand-written.
2. Session 0 ran in Plan Mode: read the spec, asked §13, planned Session 1. Done 2026-09-20.
3. Sessions 1 onward run in acceptEdits. Every build prompt references section numbers. If the
   pipeline or architecture changes, the ASCII diagram in §5 gets updated in the same session.
4. This project is data-source-heavy, so §14 (VERIFY) is not optional. Every dataset in §7 and
   §20 has a VERIFY line. Before writing a fetcher, confirm the download endpoint, format,
   resolution, vintage and license, and log it in §15. A wrong URL or a misread license corrupts
   the project more than a missing layer does.
5. Two-language repo: Python for the pipeline (`pipeline/`), TypeScript for the web app (`web/`).
   Sessions 1 to 5 are Python; 6 and 7 are TypeScript.
6. End every session by updating `CLAUDE.md` and ticking any §17 acceptance criteria that now pass.
7. Development environment note: the Claude Code cloud container blocks outbound HTTPS except to
   package registries and GitHub. Every pipeline stage therefore runs against the synthetic
   fixture world in `pipeline/fixtures/` (§11.1), and real-data fetches and the global build run
   on Saj's laptop.

## 1. Problem

Granular climate hazard tools exist (FEMA National Risk Index, NOAA CMRA, NCDP) but are US-only.
Global hazard data exists (World Bank CCKP, WRI Aqueduct, Copernicus/JRC systems) but lives in
separate portals aimed at researchers and insurers. Livability and happiness indices exist (EIU,
Happy City Index, World Happiness Report, Subnational HDI) but cover cities or countries and say
nothing about climate. Nobody has put future climate exposure and present-day wellbeing on the
same explorable map for the whole planet.

Anyone asking "what does the climate outlook and quality of life look like here" currently
cross-references five sites by hand and still cannot see the two side by side. And "quality of
life" is not one number: an early-career renter, a family choosing schools, and a queer person
looking for community weigh different things. See §18 for prior art and §20 for the
life-dimensions design that addresses this.

## 2. Goal

A free, global, explorable web map where a person can click anywhere on land and see:

- projected climate hazard exposure for a stated scenario and horizon, per hazard and combined,
- a wellbeing score for the same place at the best available resolution,
- the life dimensions they chose to weight (§20), each with its coverage and resolution,
- exactly which sources produced those numbers, their vintage, and how confident the map is.

Data gaps are shown, not hidden. Every hex carries a coverage count and a resolution tag per
dimension, and the map renders low-confidence areas visibly differently.

## 3. Non-goals (v1)

| Non-goal | Why |
|---|---|
| Telling anyone where to move | The map shows evidence and lets the person weigh it. No recommendations, no "top 10 places" feed. |
| Property-level or street-level resolution | H3 hexes at tens of km. Insurers and Climate Central do parcel-level; that is not this. |
| Real-time hazard monitoring | GloFAS and GWIS already do that. This is about projected exposure. |
| Any paid or scrape-restricted data | No EIU full dataset, no Maplecroft, no Numbeo scraping, no Walk Score, no Cook PVI. |
| Multiple scenarios and horizons in v1 | One moderate pathway, one horizon (§13.3). Toggles are v2. |
| User accounts, saved views, comments | URL state is the save mechanism. |
| Predictions presented as certainties | Scenario and horizon are always visible in the UI and inspector. |
| Non-climate hazards (earthquake, volcano) | Data exists (GEM). v2, clearly labeled as non-climate (§13.6). |
| Commercial use | Non-commercial for the foreseeable future (§13.13). Two sources depend on it. |

## 4. Product invariants (must stay true in every version)

1. **Every number on screen is traceable.** The inspector shows source, vintage, scenario and
   processing note for each value. `/methodology` is generated from the pipeline manifest.
2. **Resolution mismatch is labeled, never smoothed over.** Hazard values are per hex. Every
   other dimension carries a resolution tag: `hex` (computed per hex from a raster or point set),
   `basin` (a hydrological sub-basin polygon at the centroid), `admin1`, `county`, `tract`,
   `national`, or `none`.
3. **No data is not zero risk.** Hexes with missing layers render as visibly uncertain, and
   composites exclude missing layers rather than treating them as 0.
4. **Only open-licensed data with attribution.** Every source's license is in the manifest and on
   `/methodology`. If a license cannot be confirmed, the layer does not ship. The `fetch` stage
   refuses sources whose license is still `VERIFY`.
5. **Static-first.** All heavy computation happens in the offline pipeline. The web app serves
   pre-built tiles from R2 and does no per-request geoprocessing.
6. **Composite scores are transparent and adjustable.** The default view is a bivariate
   choropleth that needs no weighting. Any single-number composite exposes its weights as sliders.
7. **No trackers, no analytics scripts, no accounts.**
8. **Not every dimension has a "better".** Composition dimensions (§20.2) are matched to what the
   person picks, never ranked by the pipeline.

## 5. Architecture and data flow

**Stack.** Pipeline: Python 3.11+, `rasterio`, `xarray`, `geopandas`, `shapely`, `h3` (v4 API),
raster-to-H3 by rasterizing hex ids per window and grouping with numpy (§15.11; h3ronpy was evaluated and rejected), `pyarrow`, `tippecanoe`
(felt fork, built from source) for tiles, `pmtiles` CLI, `rclone` or the AWS CLI for R2 upload.
No PostGIS (§13.7). Web: Next.js 16 static export (TypeScript) on Cloudflare Pages, MapLibre GL JS
v6, `pmtiles` 4, Tailwind. Tiles and manifest on Cloudflare R2 (public bucket, custom domain,
CORS). No database in the web app.

```
  OPEN DATA SOURCES  (fetched once per refresh, cached under data/raw/, never committed)

  HAZARD (raster / vector)                 WELLBEING + LIFE DIMENSIONS (tabular + polygons)   REFERENCE
  - WB CCKP CMIP6 hd35: hot days > 35C     - Global Data Lab Subnational HDI (admin1)         - geoBoundaries CGAZ admin0 + admin1
  - WRI Aqueduct Floods riverine 1-in-100  - World Happiness Report ladder (national)         - Natural Earth 10m land polygons
  - WRI Aqueduct Floods coastal 1-in-100   - World Bank GSAP poverty (admin1)                 - JRC GHSL GHS-POP 1 km
  - WRI Aqueduct 4.0 future water stress   - OECD Regional Well-Being (TL2), ILOSTAT (nat.)
                                           - US: Census ACS, MEDSL, EPA SLD, Urban Inst., HRSA
        |                                          |                                                |
        v                                          v                                                v
  +--------------------------------------------------------------------------------------------------------+
  |                        pipeline/  (Python CLI:  python -m pipeline [--fixtures] [--res 4] [--bbox ...] <stage>)|
  |                                                                                                        |
  |  fetch     download + sha256 each source per pipeline/sources.yaml -> data/raw/<id>/                  |
  |            manual sources (GEE export, registration) are checked for presence, recipe printed         |
  |  grid      Natural Earth land -> H3 cells at H3_RES (drop ocean) -> data/interim/hexes_r{res}.parquet |
  |  pop       GHSL 1 km -> sum per hex -> population, inhabited flag (pop >= POP_MIN)                    |
  |  admin     hex centroid -> geoBoundaries admin0/admin1 -> iso_a2, admin1_id, admin1_name              |
  |  hazards   for each raster: windowed read -> raster_to_h3 -> aggregate per hex (§8.1)                 |
  |            -> per-hazard 0-100 percentile score + *_ok flag                                           |
  |  dims      for each dimension in pipeline/dimensions.yaml, run its joiners (§20.3):                    |
  |            polygon_centroid | iso_lookup | area_weighted_overlay | point_density                      |
  |            -> {id}_raw, {id}_res ('hex' | 'basin' | 'admin1' | 'county' | 'tract' | 'national' | 'none') |
  |  score     exposure = mean(available hazard scores), coverage = count(*_ok)                            |
  |            {id}_score = percentile within the dimension's coverage domain (§8.2, §20.4)               |
  |            wb_score, bivar class 1-9 (§8.4)                                                            |
  |  export    data/out/hexes_r{res}.parquet + manifest.json (§6.3); --geojson for tippecanoe             |
  |  tiles     python tiler (pipeline/tiler.py; tippecanoe optional) -> hexes.pmtiles                     |
  |            hex4 layer z2-4 (slim attrs at z2), hex5 layer z5-7, overzoomed beyond (§9, §13.18)       |
  |  publish   hexes.pmtiles + manifest.json -> R2 via boto3 (.env) or web/public/data (local) (§13.24)   |
  +-----------------------------------------------+--------------------------------------------------------+
                                                  |  static files only
                                                  v
  +----------------------------------------+    range      +------------------------------------------+
  |  web/  Next.js 16 static export        | <--requests-- |  Cloudflare R2 (public, custom domain)   |
  |  on Cloudflare Pages                   |               |  hexes.pmtiles   manifest.json           |
  |  MapLibre GL JS v6 + pmtiles protocol  |               |  (basemap: OpenFreeMap, §13.5)           |
  |  views: bivariate | per hazard |       |               +------------------------------------------+
  |         wellbeing | my priorities      |
  |  presets + sliders (§20.5), legend,    |
  |  click -> inspector (feature props)    |
  |  URL state  ?lat&lng&z&view&w=         |
  |  /methodology rendered from manifest   |
  +----------------------------------------+
```

There is no API in v1. The inspector reads attributes straight from the vector tile feature, which
is why every displayed value has to be baked into the hex attributes in §6.

## 6. Data model

### 6.1 Hex record (one row per H3 cell, both resolutions)

```
h3            string   H3 index (hex string)
res           int      4 or 5
lat, lng      float    cell centroid
iso_a2        string   country of centroid (geoBoundaries admin0), null if disputed/none
admin1_id     string   geoBoundaries admin1 shapeID of centroid (pinned release), null if none
admin1_name   string
population    int      GHSL sum, 0 if none
inhabited     bool     population >= POP_MIN (default 100)

-- hazards: raw value, 0-100 score, has_data flag (one triplet per hazard, §8)
heat_days     float    projected annual days Tmax > 35C
heat_score    int
heat_ok       bool
rflood_frac   float    fraction of hex area with riverine 1-in-100 inundation depth >= DEPTH_MIN
rflood_score  int
rflood_ok     bool
cflood_frac   float    same for coastal
cflood_score  int
cflood_ok     bool
wstress_cat   int      Aqueduct future water stress category 0-4 (-1 = arid/low water use, treated separately)
wstress_score int
wstress_ok    bool

-- composites
coverage      int      count of *_ok true (0-4)
exposure      int      mean of available hazard scores, null if coverage = 0
wb_value      float    wellbeing raw (SHDI 0-1 or WHR ladder 0-10)
wb_score      int      0-100, normalized within its source (§8.3)
wb_source     string   'shdi' | 'whr' | none
wb_res        string   'admin1' | 'national' | 'none'
bivar         int      1-9 bivariate class (§8.4), 0 if exposure or wb_score is null
scenario      string   'rcp45_ssp245'
horizon       string   '2050'

-- life dimensions (§20): per dimension id, one of
{id}_raw, {id}_score, {id}_res                      kind = score
{id}_lean, {id}_res                                 kind = signed  (-100..100)
{id}_w, {id}_b, {id}_h, {id}_a, {id}_o, {id}_maj, {id}_res   kind = composition (integer percents)
```

Keep attribute names short and typed; they ship in every tile. Null attributes cost nothing in
MVT, so US-only attributes on non-US hexes add no tile weight. Anything not needed by the
inspector or the styling stays in the parquet, not the PMTiles.

### 6.2 pipeline/sources.yaml (one entry per dataset)

```yaml
- id: aqueduct_floods_river
  name: WRI Aqueduct Floods, riverine inundation depth
  group: hazard
  access: manual            # direct | manual (GEE export, registration) | fixture
  url: VERIFY               # or the confirmed URL; manual sources carry a recipe instead
  format: geotiff
  crs: EPSG:4326
  native_res_m: ~1000
  scenario: rcp45
  horizon: 2050
  return_period: 100
  license: VERIFY           # fetch refuses VERIFY; expected "CC BY 4.0"
  license_note: ""          # e.g. "non-commercial only"
  vintage: VERIFY
  attribution: "World Resources Institute, Aqueduct Floods"
  processing: "fraction of hex pixels with depth >= 0.15 m"
  files: [inunriver_rcp4p5_0000GFDL-ESM2M_2050_rp00100.tif]
  checksum: null            # filled by fetch into data/raw/CHECKSUMS
```

### 6.3 manifest.json (written by publish, consumed by /methodology and the inspector)

```json
{
  "built_at": "2026-...",
  "h3_res": [4, 5],
  "scenario": "rcp45_ssp245",
  "horizon": "2050",
  "non_commercial": true,
  "tiles": {"hexes": {"key": "hexes.pmtiles", "sha256": "..."}},
  "sources": [ { "...each sources.yaml entry with checksum and row counts..." : "" } ],
  "dimensions": [ { "...each dimensions.yaml entry with coverage counts by _res..." : "" } ],
  "coverage_summary": {"hexes_total": 0, "hexes_full_coverage": 0, "wb_admin1": 0, "wb_national": 0, "wb_none": 0},
  "processing_notes": ["heat: CMIP6 ensemble median, 2040-2059 vs 1995-2014", "..."]
}
```

## 7. Data sources (v1) and what each contributes

Every row has a VERIFY item in §14 and a §15 log line. See §20.6 for the life-dimension sources.

| Layer | Source | Resolution / unit | Scenario, horizon | License | Notes |
|---|---|---|---|---|---|
| Extreme heat | World Bank CCKP, CMIP6 ensemble, `hd35` (days Tmax > 35C) | 0.25° NetCDF, EPSG:4326 | SSP2-4.5, 2040-2059, ensemble median | CC BY 4.0 (§15.1) | Public S3 `wbg-cckp`, us-west-2. Do not use `hi35` (heat index). |
| Riverine flood | WRI Aqueduct Floods, inundation depth | ~1 km GeoTIFF | RCP4.5, 2050, 1-in-100 | CC BY 4.0 (§15.2) | S3 copies removed; one-time Google Earth Engine export (§13.11). |
| Coastal flood | WRI Aqueduct Floods, coastal with subsidence | ~1 km GeoTIFF | RCP4.5, 2050, 1-in-100, 50th pct SLR | CC BY 4.0 (§15.2) | Same family and access path as riverine. |
| Water stress | WRI Aqueduct Water Risk Atlas 4.0, future | polygons (basin x province x aquifer) | 2050 business-as-usual (`bau50_ws_x_c`) | CC BY 4.0 (§15.3) | Vector: join hex centroid to polygon. -1 = arid/low use. |
| Wellbeing (subnational) | Global Data Lab, Subnational HDI 8.3 | admin1 polygons, ~1,800 regions | latest year | Free with citation, **non-commercial**, registration (§15.4) | Join on GDL-Code via GDL shapefiles; crosswalk to geoBoundaries names. |
| Wellbeing (national fallback) | World Happiness Report 2026, ladder | country, 147 | 3-year rolling 2023-2025 | Free download (§15.5) | Used only where SHDI has no region. |
| Population | JRC GHSL GHS-POP R2023A | 30 arc-sec WGS84, persons per cell | epoch E2025 | CC BY 4.0 (§15.6) | Drives inhabited flag and population-weighted joins. |
| Boundaries | geoBoundaries 6.0.0 CGAZ ADM0 + ADM1 | polygons | current | CC BY 4.0 (§15.7) | Git LFS files; pin release; shapeID not stable across releases. |
| Land mask | Natural Earth 1:10m land | polygons | current | Public domain (§15.8) | Defines the hex grid extent. |

v2 sources: JRC Global Drought Observatory; Copernicus GWIS fire danger; NASA/IPCC AR6 sea level;
NOAA IBTrACS; GEM Global Seismic Hazard (CC BY-NC-SA, non-climate); Happy City Index city points
(VERIFY reuse); INFORM Subnational for comparison.

Explicitly excluded: EIU Global Liveability Index beyond public rankings, Numbeo, Maplecroft,
Walk Score, Cook PVI, GreatSchools, NHGIS and IPUMS International (no redistribution), SEDA
(non-transferable) unless permission is granted.

## 8. Scoring

### 8.1 Per-hazard raw values

- Heat: mean of the projected hot-days grid over the hex. Unit: days per year. Hexes in
  perpetually hot regions saturate near 365; the percentile rank handles that.
- Riverine and coastal flood: fraction of hex pixels with inundation depth >= DEPTH_MIN
  (0.15 m). Unit: 0 to 1. v2 replaces area fraction with GHSL-weighted population fraction.
- Water stress: Aqueduct category at hex centroid, 0 (low) to 4 (extremely high). Arid and low
  water use (-1) is stored but scored as null with `wstress_ok = false` and a processing note.

### 8.2 Per-hazard score, 0 to 100

Percentile rank across all inhabited land hexes at the same resolution, so 80 means "worse than
80% of inhabited places". Percentile rank is chosen over fixed thresholds because the hazards
have incomparable units. The raw value is always shown next to the score. Documented on
`/methodology`.

### 8.3 Wellbeing score, 0 to 100

Min-max normalized within its source (SHDI across all admin1 regions; WHR across countries).
`wb_source` and `wb_res` travel with it. Never mix the two sources in one normalization.

### 8.4 Composites

- `exposure` = mean of available hazard scores. `coverage` = how many were available (0 to 4).
  `coverage < 4` renders as reduced confidence (§9.3).
- `bivar` = 3x3 class from tercile of `exposure` by tercile of `wb_score`, computed over
  inhabited hexes. Class 0 if either side is null. Default map view; needs no weighting.
- "My priorities" (weighted view, §20.5): computed client-side from tile attributes so no rebuild
  is needed when a slider moves. Missing dimensions drop out of the denominator.

### 8.5 Sanity checks the pipeline must run and print

- Percentage of inhabited hexes with `coverage = 4`, `= 0`.
- Percentage of inhabited hexes by `wb_res`, and per life dimension by `{id}_res`.
- Spot checks: Dhaka (high flood, mid wellbeing), Phoenix (high heat, high wellbeing),
  Reykjavik (low exposure, high wellbeing), Sahel band (water stress + heat, low wellbeing).
  If any spot check looks wrong, stop and investigate before tiles are built.

## 9. Tiles and rendering

### 9.1 H3 resolution

Pipeline is resolution-agnostic (`H3_RES` list). Ship res 4 for zoom 2 to 4 and res 5 for zoom
5 to 7 (overzoomed to 12 in the client); zoom 0-1 is not built because a res-4 hex is under two
pixels there and the world tile would exceed 5 MB. Res 5 has about 2 million cells globally, roughly 600k on land. Iterate on res 4 alone
during Sessions 1 to 4 for speed.

### 9.2 Tile build

Built by `pipeline/tiler.py` (pure Python: `mapbox-vector-tile` + the `pmtiles` writer, decision
§13.18) with two layers: `hex4` for zoom 2-4 (the slim attribute set at zoom 2, where a res-4 hex
is about two pixels) and `hex5` for zoom 5-7; MapLibre overzooms the zoom-7 tiles beyond that
without further requests. tippecanoe (felt fork) remains an optional backend when it is on PATH
(`tiles --backend tippecanoe` after `export --geojson`). Upload to R2; CORS per §15.14; the web
app reads the PMTiles via HTTP range requests.

### 9.3 Styling rules (MapLibre style spec, data-driven)

- Default layer: `bivar` classes 1 to 9 with a standard bivariate palette; class 0 neutral grey.
- Per-hazard and per-dimension layers: `*_score` sequential ramp; `*_ok = false` or `*_res =
  'none'` in grey.
- Confidence: `coverage < 4` gets a hatch `fill-pattern` overlay (§13.4); `wb_res = 'national'`
  a thin dashed outline; `wb_res = 'none'` grey on wellbeing views.
- `inhabited = false` hidden by default, toggle to show (§13.8).
- Legend is a 3x3 bivariate grid with axis labels "more climate exposure" and "higher
  wellbeing", plus a confidence key and, in the priorities view, a coverage chip per dimension.

### 9.4 Basemap

OpenFreeMap (free vector tiles, no key, no signup). Style `positron`. Attribution "OpenFreeMap
© OpenMapTiles Data from OpenStreetMap". One-person service with no SLA; if it goes away, the
fallback is a Protomaps basemap PMTiles extract self-hosted on R2. Never Mapbox, never ArcGIS.

## 10. Web app surfaces

- `/`: full-screen map. Left panel: view selector (Bivariate | Heat | Riverine flood | Coastal
  flood | Water stress | Wellbeing | My priorities), preset picker and sliders visible only in
  My priorities, scenario and horizon as a static label, confidence toggle, inhabited toggle,
  legend.
- Inspector (click a hex): country and admin1 name, population, each hazard's raw value and
  score with its `_ok` state, wellbeing value with `wb_source` and `wb_res` badge, coverage
  "3 of 4 hazard layers", bivariate class in words, each life dimension's value and resolution
  badge (or "no data here"), one "Sources" disclosure listing the manifest entries.
- URL state: `?lat=&lng=&z=&view=&preset=&w=<csv weights>&conf=&inh=` so any view is
  shareable. No server state.
- `/methodology`: generated from `manifest.json` at build time.
- `/about`: what this is and is not (§3 in plain language), including "does not recommend
  where to live" and the non-commercial statement.

Search by place name is v2.

## 11. Pipeline operations

- Global runs happen on Saj's laptop (Ryzen 7, 16 GB assumed). GitHub Actions runners (~7 GB
  RAM) are not enough for global 1 km rasters; the pipeline uses windowed reads and per-region
  chunks so it fits laptop RAM. Actions only runs lint and tests on fixtures.
- `data/raw/` is gitignored and can be tens of GB. `data/raw/CHECKSUMS` is committed so a fresh
  clone can verify what it downloaded.
- Every stage is idempotent and skips work when outputs exist and inputs are unchanged.
- Every stage takes `--bbox minlng,minlat,maxlng,maxlat` to run on a subregion.
- Refresh cadence: quarterly, manual. `manifest.built_at` and per-source vintage make staleness
  visible on `/methodology`.
- Logs: each stage prints row counts and the §8.5 sanity checks; `pipeline/timing.py` records
  wall time and peak RSS per stage in `data/interim/timings.json` (copied into the manifest).
- `--bbox` runs write to `data/interim/bbox_<box>/` and `data/out/bbox_<box>/` so spot checks
  never overwrite the global outputs; extracted archives and prepared layers are shared.
- Res-4 global run, 2026-09-22 (Ryzen 7 5800HS, 16 GB): grid 32 s / 0.2 GB, pop 57 s / 1.2 GB,
  admin 5 s / 1.6 GB, hazards 1,256 s / 1.3 GB (six global 1 km rasters in full-width strips),
  dims 378 s / 6.0 GB (the US tract overlay dominates), score 0.5 s, export 1 s. 81,413 land
  hexes, 50,936 inhabited, 7.72 billion people; 88.9% of inhabited hexes have all four hazards.

### 11.1 Fixture world

`pipeline/fixtures/make_fixtures.py` deterministically generates a synthetic 4° x 4° region:
land polygon with a coast, two countries and five admin1 regions, a population raster with
towns, four hazard inputs (heat NetCDF, two flood GeoTIFFs, water-stress polygons), and small
tabular files for wellbeing and life dimensions. `python -m pipeline --fixtures <stage>` runs
against it; tests use it. Real data never enters the repo.

## 12. Resolution mismatch: the decision, stated once

Hazard data is gridded and global at roughly 1 km, so hazards are computed per H3 hex. Wellbeing
and most life dimensions do not exist at that resolution; the best global option is admin1, with
national fallback, and in the US county or tract aggregates. Decision: keep hazards at hex
resolution, attach everything else at the best available coarser resolution, and label the
resolution on every hex and every dimension. Do not aggregate hazards up to admin1 or national,
because that would hide exactly the within-region variation the map exists to show.

## 13. Decisions (Session 0, 2026-09-20)

1. **Project name:** `livability-map` as working name; product name before deploy.
2. **H3 resolutions:** 4 + 5.
3. **Scenario and horizon:** moderate pathway (RCP4.5 for Aqueduct, SSP2-4.5 for CCKP), 2050.
4. **Confidence rendering:** hatch pattern.
5. **Basemap:** OpenFreeMap.
6. **GEM seismic in v1:** no; v2 as a labeled non-climate layer.
7. **PostGIS:** no; geopandas only.
8. **Hide uninhabited hexes by default:** yes, with toggle.
9. **POP_MIN / DEPTH_MIN:** 100 people / 0.15 m.
10. **Visual identity:** new system (CivicRadar not available in the build environment).
11. **Flood rasters:** Aqueduct Floods via a one-time Google Earth Engine export on Saj's laptop
    (the public S3 copies are gone, §15.2). Recipe in `docs/gee-export.md`.
12. **Life-dimension scope:** global core + US detail layers; the UI shows coverage per layer
    and never substitutes a national number for a missing subnational one without saying so.
13. **Commercial use:** non-commercial for the foreseeable future. SHDI's non-commercial terms
    are accepted and recorded in the manifest.
14. **Web host:** Cloudflare Pages instead of Vercel (same account as R2, no commercial-use gate
    on the free tier).
15. **Personalization UI:** presets (named weight sets) plus per-dimension sliders.
16. **Compute:** global build on Saj's laptop; the repo develops and tests against fixtures.
17. **Python:** `>=3.11`.

Decisions taken while building Sessions 2-7 (2026-09-22):

18. **Tiler:** pure-Python (`pipeline/tiler.py`) because tippecanoe has no Windows build; tippecanoe
    stays an optional backend. Zoom plan hex4 z2-4 (slim attributes at z2), hex5 z5-7 + overzoom.
19. **Aqueduct Floods** are fetched directly from `https://aqueduct.wridata.org/AqueductFloods20/`
    (confirmed 2026-09-22); the Earth Engine recipe in `docs/gee-export.md` is a fallback only.
20. **ACS B09019** (same-sex spouse + same-sex unmarried partner) replaces B11009, which the
    2020-2024 table-based Summary File publishes only for state and above.
21. **OECD TL2 geometry** is derived from geoBoundaries ADM1 by name crosswalk with the OECD
    Territorial correspondence table (TL2 names, else TL3 names dissolved to their TL2 parent),
    with manual overrides in `pipeline/crosswalks/oecd_tl2_adm1.csv`. 77% of TL2 regions (593/772,
    369 with well-being scores) are geolocated; Italy, Ireland, the UK, Greece and Costa Rica use
    different units and stay `none`. The report is in `data/interim/prep/oecd_tl2_report.json`.
22. **OECD data license:** OECD Terms and Conditions §3 (use, adapt and distribute for any purpose
    with the OECD citation), confirmed first-hand 2026-09-22; recorded as such, not as CC BY.
23. **Wellbeing sources:** WHR 2026 `WHR26_Data_Figure_2.1.xlsx` (Year 2025 rows, column
    `Life evaluation (3-year average)`); SHDI v10.2 is login-gated and dropped in by hand.
24. **Publishing:** R2 via boto3 with `.env` credentials; Pages via `npx wrangler pages deploy`;
    `publish --target local` copies to `web/public/data/` for development.
25. **Score convention:** every `{id}_score` is the plain midrank percentile of the raw value in its
    domain; direction (`higher_is`) is applied by the client, never encoded in the score.
26. **MEDSL download:** Harvard Dataverse now requires a guestbook response; `access: dataverse`
    reads `DATAVERSE_GUESTBOOK_*` from `.env` and otherwise prints the manual recipe.
27. **Prep layer:** format-specific parsing lives in `pipeline/prep/<source>.py`, one loader per
    source, producing the columns `dimensions.yaml` names; joiners stay generic.
28. **Present-day environment is its own group (`env`), not a hazard.** Air quality, tree cover,
    wildfire (observed burned area 2001-2020) and drought risk (Aqueduct baseline) are shown
    beside the four 2050 hazards and can be weighted in My priorities, but `exposure`,
    `coverage` and the bivariate class stay the four projected hazards so the map's headline
    axis keeps one scenario and one horizon (2026-09-22).
29. **Hex-level layers** are joined by two new joiners (`raster_mean`, `point_mean`, §20.3) and
    carry the resolution tag `hex`; Aqueduct sub-basins sampled at the centroid carry `basin`.
    Rasters that are not plain GeoTIFFs (the ACAG PM2.5 NetCDF, the GFED5 monthly burned-area
    files) are built once into `data/interim/prep/<id>.tif` by `pipeline/prep/rasters.py`.
30. **Non-commercial sources are acceptable** (Saj, 2026-09-22): the project is non-commercial
    (§13.13), so Ookla's CC BY-NC-SA 4.0 speed tiles are in; the ShareAlike clause is honoured
    by labelling the derived `net_*` attributes CC BY-NC-SA 4.0 in the registry and manifest.
    HUD's Fair Market Rents workbook is `access: manual` because huduser.gov answers every
    non-browser client with an empty 202 (an AWS WAF challenge); the pipeline does not
    impersonate a browser.

## 14. VERIFY before code depends on it

1. WB CCKP: indicator code, download format, license.
2. Aqueduct Floods: hosting, file naming, CRS, nodata, license.
3. Aqueduct Water Risk Atlas 4.0: future projection field names, polygon unit, license.
4. Global Data Lab SHDI: download path, registration, license, polygon file and identifiers.
5. World Happiness Report: data download, terms, report year.
6. GHSL GHS-POP: epoch, product, reuse conditions.
7. geoBoundaries: version, license, shapeID stability.
8. Natural Earth: public domain, 10m land file.
9. Basemap: OpenFreeMap availability and attribution.
10. PMTiles size at res 4 + 5 with all attributes; if over ~300 MB, trim or split.
11. h3ronpy current API and maintenance; fallback path.
12. tippecanoe version supports `.pmtiles` output.
13. MapLibre pmtiles protocol setup for the current major version.
14. R2 CORS configuration for range requests.
15. Each §20.6 life-dimension source: endpoint, resolution, license.

## 15. Verification log

Status key: **search** = found via search results and S3/registry probes from a network-restricted
container, not a first-hand page read; **confirmed** = fetched and inspected. Everything below is
**search** until re-checked from a network-open machine.

| Date | Item | Result | Source URL |
|---|---|---|---|
| 2026-09-20 | 14.1 CCKP hd35 | search. Gridded 0.25° NetCDF on public S3 `wbg-cckp` (us-west-2; other regions 301). File `climatology-hd35-annual-mean_cmip6-x0.25_ensemble-all-ssp245_climatology_median_2040-2059.nc` (~416 KB). CC BY 4.0. `hi35` is heat index, not this. | https://wbg-cckp.s3.us-west-2.amazonaws.com/data/cmip6-x0.25/hd35/ensemble-all-ssp245/ ; https://github.com/worldbank/climateknowledgeportal/blob/main/docs/collections/cmip6-x0.25.md |
| 2026-09-20 | 14.2 Aqueduct Floods | search, **DEAD at S3**. `wri-projects/AqueductFloodTool/download/v2/` returns 404 and lists zero keys. Data survives on Google Earth Engine `WRI/Aqueduct_Flood_Hazard_Maps/V2`. Naming: `inunriver_rcp4p5_{model14}_2050_rp00100.tif` (models 00000NorESM1-M, 0000GFDL-ESM2M, 0000HadGEM2-ES, 00IPSL-CM5A-LR, MIROC-ESM-CHEM), `inuncoast_rcp4p5_wtsub_2050_rp0100_0.tif`. 30 arc-sec, EPSG:4326, Float32 m, nodata -9999. CC BY 4.0. Decision §13.11. Check the WRI page for a new link before Session 2. | https://www.wri.org/data/aqueduct-floods-hazard-maps ; https://developers.google.com/earth-engine/datasets/catalog/WRI_Aqueduct_Flood_Hazard_Maps_V2 |
| 2026-09-20 | 14.3 Aqueduct 4.0 | search. CC BY 4.0. Future water stress category `bau50_ws_x_c`, raw `bau50_ws_x_r`; baseline uses `bws_cat`. -1 = arid/low use. Polygons are basin (6-digit Pfafstetter) x province x aquifer unions. GeoPackage + CSV download. | https://www.wri.org/data/aqueduct-global-maps-40-data ; https://github.com/wri/Aqueduct40/blob/master/data_dictionary_water-risk-atlas.md |
| 2026-09-20 | 14.4 GDL SHDI | search. v8.3 (2025-09-16), ~1,800 regions. Free registration required. Terms: "freely downloaded and used for noncommercial purposes ... provided that the Global Data Lab is mentioned as the source". Shapefiles keyed by GDL-Code. Accepted under §13.13. | https://globaldatalab.org/shdi/download/shdi/ ; https://globaldatalab.org/shdi/shapefiles/ ; https://globaldatalab.org/termsofuse/ |
| 2026-09-20 | 14.5 WHR | search. WHR 2026 (2026-03-20), 147 countries, ladder is a 3-year rolling average 2023-2025. Figure 2.1 data free to download; Gallup microdata is not. Exact xlsx filename to copy from the data-sharing page. | https://www.worldhappiness.report/data-sharing/ ; https://data.worldhappiness.report/table |
| 2026-09-20 | 14.6 GHS-POP | search. R2023A is current (1975-2030; 2025 and 2030 are projections). Use `GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip` (~450 MB), values are persons per cell so per-hex sum = population. CC BY 4.0, no registration. | https://human-settlement.emergency.copernicus.eu/ghs_pop2023.php ; https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/ |
| 2026-09-20 | 14.7 geoBoundaries | search. 6.0.0 (2023-09-14) is the latest tagged release. CGAZ ADM0/ADM1 gpkg via GitHub `/raw/` which 302s to media.githubusercontent.com (Git LFS; raw.githubusercontent.com returns a pointer file). CC BY 4.0 (gbOpen track). shapeID not stable across releases; pin 6.0.0. | https://github.com/wmgeolab/geoBoundaries/tree/main/releaseData/CGAZ |
| 2026-09-20 | 14.8 Natural Earth | search. Public domain ("No permission is needed to use Natural Earth"). | https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip |
| 2026-09-20 | 14.9 Basemap | search. OpenFreeMap live, no key, styles `liberty`/`positron`/`bright`; attribution "OpenFreeMap © OpenMapTiles Data from OpenStreetMap". Protomaps hosted free tier is non-commercial with a key; Protomaps daily planet PMTiles builds can be extracted by bbox for self-hosting. | https://openfreemap.org/quick_start/ ; https://docs.protomaps.com/basemaps/downloads |
| 2026-09-20 | 14.11 h3ronpy | confirmed installs (0.22.0, Nov 2024; author seeking maintainers). API is `h3ronpy.raster.raster_to_dataframe(array, transform, h3_resolution, nodata_value, compact)`; takes numpy + affine, not files. Uses Rust h3o (H3 v4 semantics). Fallback implemented in `pipeline/h3util.py`: rasterize hex ids per window, group with bincount. h3-py 4.5.0. | https://h3ronpy.readthedocs.io/en/stable/usage/raster.html |
| 2026-09-20 | 14.12 tippecanoe | search. felt fork writes `.pmtiles` directly (`-o out.pmtiles`). Latest tag 2.79.0 (2025-07-24); `main` says 2.82.0. Build from source; the Ubuntu apt package is the archived Mapbox version without PMTiles output. | https://github.com/felt/tippecanoe |
| 2026-09-20 | 14.13 MapLibre | search. maplibre-gl 6.10.0: ESM-only, no default export, WebGL2 required, worker loaded by URL (`setWorkerUrl` for bundlers), nested GeoJSON properties preserved. `addProtocol("pmtiles", new Protocol().tile)` unchanged. pmtiles npm 4.5.0. | https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/ |
| 2026-09-20 | 14.14 R2 CORS | search. AllowedHeaders must include `range` and `if-match`; ExposeHeaders `ETag, Content-Length, Content-Range, Accept-Ranges`. Use a custom domain (r2.dev is rate-limited). Purge cache after CORS edits; a CORS error with no `cf-cache-status` header is Hotlink Protection. | https://developers.cloudflare.com/r2/buckets/cors/ |
| 2026-09-20 | Web host | search. Next.js 16.3.x (Node >= 20.9). Vercel Hobby forbids commercial use and caps transfer at 100 GB/month. Decision §13.14: Cloudflare Pages. | https://vercel.com/docs/plans/hobby |
| 2026-09-22 | 14.1 CCKP hd35 | **confirmed**: 416 KB NetCDF, variable `climatology-hd35-annual-mean` (time, lat, lon), lon -180..179.75, values over oceans too. | as above |
| 2026-09-22 | 14.2 Aqueduct Floods | **confirmed**: direct mirror `https://aqueduct.wridata.org/AqueductFloods20/` serves all six GeoTIFFs (5 x ~92 MB riverine, 47 MB coastal; 21600 x 43200, EPSG:4326, nodata -9999, striped LZW, files dated 2026-03-27). GEE catalog terms: "available without restriction on use or distribution", attribution requested. Decision §13.19. | https://aqueduct.wridata.org/AqueductFloods20/ ; https://datasets.wri.org/datasets/aqueduct-floods-hazard-maps |
| 2026-09-22 | 14.3 Aqueduct 4.0 | **confirmed**: `https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip` (249 MB) is a File Geodatabase (`Aq40_Y2023D07M05.gdb`, layer `future_annual`, field `bau50_ws_x_c`) plus CSVs; CC BY 4.0 per the wri/Aqueduct40 README. | https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip |
| 2026-09-22 | 14.4 GDL SHDI | **confirmed** terms (non-commercial, citation); current version v10.2 (2026-05-13), downloads login-gated: `Subnational HDI Data v10.2.csv` and the GDL shapefile zip. | https://globaldatalab.org/shdi/archive/ ; https://globaldatalab.org/termsofuse/ |
| 2026-09-22 | 14.5 WHR | **confirmed**: `https://files.worldhappiness.report/WHR26_Data_Figure_2.1.xlsx` (134 KB), 2011-2025 panel, column `Life evaluation (3-year average)`; 147 countries for 2025 after name mapping. No explicit license text; citation requested. | https://www.worldhappiness.report/data-sharing/ |
| 2026-09-22 | 14.6-14.8 GHSL, geoBoundaries, Natural Earth | **confirmed** by download and use: GHSL zip contains a 21384 x 43202 float64 tiled GeoTIFF (extracted once); geoBoundaries gpkg via media.githubusercontent.com; Natural Earth zip read directly. Some geoBoundaries names are mojibake (repaired in `prep.util.fix_mojibake`). | as above |
| 2026-09-22 | 14.10 PMTiles size | res 4 global archive built by the python tiler; see `data/out/tiles_report.json` (res 5 pending). | - |
| 2026-09-22 | 14.12 tippecanoe | **confirmed** no Windows build (no release binaries, no conda-forge win-64, no MSYS2 package). Decision §13.18. | https://github.com/felt/tippecanoe/releases |
| 2026-09-22 | 14.13 MapLibre | **confirmed** in the browser: maplibre-gl 6.10.0 ESM, `setWorkerUrl` needed because the worker and its `maplibre-gl-shared.mjs` are resolved relative to the module URL (both copied to `public/` by `web/scripts/copy-worker.mjs`); `addProtocol("pmtiles", new Protocol().tile)` unchanged; pmtiles 4.5.0. | https://maplibre.org/maplibre-gl-js/docs/ |
| 2026-09-22 | 14.14 R2 CORS | rules written by `publish --target r2` (`range`, `if-match` allowed; `etag`, `content-length`, `content-range`, `accept-ranges` exposed) and checked with a Range request; not yet exercised against a real bucket (credentials pending). | https://developers.cloudflare.com/r2/buckets/cors/ |
| 2026-09-22 | 14.15 life dimensions | **confirmed** every endpoint: GSAP xlsx + 2023 gpkg (CC BY 4.0, key `geo_code`, 1,914 regions); OECD RWB xlsx (`Score_Last`, header row 7) and OECD Territorial correspondence TL2024c (header row 3); ILOSTAT via `rplumber.ilo.org` CSV API (CC BY 4.0, 217 countries); ACS 2024 5-year table-based SF (8 tables, tract rows `1400000US`, 85,382 tracts; B11009 has no tract rows, §13.20); cartographic tracts/counties 2025 (`GEOIDFQ` = ACS `GEO_ID`); MEDSL v20.0 CC0 behind a guestbook (§13.26); EPA SLD v3 (553 MB File GDB, layer `EPA_SLD_Database_V3`, 220,739 block groups, D4C present for 101,421); Urban Institute EDFacts 2019 (ODC-BY, negative rates are suppression codes) + NCES EDGE TL25 boundaries (9,313 districts matched); HRSA AHRF 2024-2025 CSV (`md_nf_activ_23`, 3,213 counties). | sources.yaml |
| 2026-09-22 | 8.5 spot checks (res 4) | Dhaka: 34 hot days, riverine 18.0% of area, coastal 19.9%, water stress 4. Phoenix: 143 hot days, riverine 1.7%, coastal 0, stress 4. Reykjavik (nearest land hex: the city's cell centre is at sea): 0 hot days, riverine 3.1%, coastal 0.1%, stress 0. Niamey: 252 hot days, riverine 8.3%, coastal 0, stress 4. All plausible. | - |
| 2026-09-22 | 20.6 cost / rent | **confirmed** BEA SARPP.zip / MARPP.zip (LineCode 1 all-items RPP, 2024, US = 100; GeoFIPS quoted and space-padded, four footer lines); Census GENZ2025 CBSA and state cartographic files; World Bank ICP 2021 household price level (source 90, series 9100000, 1,449 records, World = 100) and WDI `PA.NUS.PPPC.RF` (a US = 1 ratio, rescaled onto the ICP base with the median ratio over shared countries); HUD FY26_FMRs.xlsx is 376,572 bytes with a browser but an empty 202 for any other client (§13.30, manual). | sources.yaml |
| 2026-09-22 | 20.6 extras | **confirmed** MAP motorized travel time (WCS GetCoverage, 43200 x 17400 float32 tiled 512, -9999 nodata, 3,030,408,164 bytes streamed chunked in 8 min; CC BY 4.0 per the GEE catalog entry); ACAG SatPM2.5 V6.GL.03 2024 (`s3://satpmdata`, 450 MB NetCDF-4, `PM25` ug/m3, 0.01°, 60S-70N, lat ascending, water masked with negative values not NaN; CC BY 4.0); CGLS-LC100 tree-cover fraction 2019 (Zenodo 3939050, 5,650,453,608 bytes, uint8 255 nodata, tiled 256 DEFLATE; CC BY 4.0); Ookla 2026 Q2 fixed (353,986,294 B) and mobile (184,560,046 B) parquet, columns `quadkey, tile, tile_x, tile_y, avg_d_kbps, avg_u_kbps, avg_lat_ms, avg_lat_down_ms, avg_lat_up_ms, tests, devices`, **CC BY-NC-SA 4.0** (not BY-NC as first noted); GFED5 BA.zip (Zenodo 7668424, 264,817,204 B, 288 monthly `BA{YYYYMM}.nc` 1997-2020, variables Norm/Peat/Defo/Total/Crop with no units attribute, km2 per the readme, ocean = 0; CC BY 4.0); Aqueduct 4.0 `baseline_annual.drr_cat` (-9999 on 15,899 of 68,506 sub-basins; `future_annual` has no drought field). GWIS country profiles have no documented download and were dropped. | sources.yaml, docs/superpowers/plans/2026-09-22-cost-rent-and-extras.md |
| 2026-09-22 | 9.2 res-5 tiles | the first res-5 tile build died with `BrokenProcessPool`: every encoder process turned all ~80 attributes of 570,143 hexes into Python objects at start-up (~1.7 GB each, 15 processes). The worker store is now typed numpy arrays with categorical strings, converted per feature, and the pool is capped by free memory (`tiler.default_workers`). | pipeline/tiler.py |
| 2026-09-22 | 8.5 spot checks, cost + extras (res 4) | Dhaka: care 7 min, PM2.5 82 ug/m3, trees 21%, net 95 Mbps. Phoenix: care 3 min, PM2.5 8.7, trees 1.7%, net 380 Mbps, cost 104 (BEA metro). Reykjavik (nearest land hex): care 33 min, PM2.5 4.3, trees 1.4%, net 238 Mbps. Niamey: care 24 min, PM2.5 23, trees 2.0%, net 32 Mbps. Inhabited coverage: care 100%, air 99.9%, trees 100%, fire 100%, drought (basin) 92%, net 70% (Ookla holes), cost 99.5% (metro 2.6%, state 5.4%, national 91.5%), rent 0% until the HUD workbook is saved by hand. dims res 4 took 2,506 s (tree cover 536 s, SLD overlay 601 s), peak 7.6 GB. | pipeline sanity |
| 2026-09-20 | 14.15 life dimensions | search. See §20.6 table and notes. | see §20.6 |

## 16. Phasing and session plan

**v1.** Pipeline for 4 hazards + SHDI/WHR wellbeing + GHSL population at res 4 and 5; percentile
scores; bivariate class; global life dimensions (GSAP, OECD, ILOSTAT) and US life dimensions
(ACS, MEDSL, EPA SLD, Urban Institute, HRSA); manifest; PMTiles on R2; MapLibre map with
bivariate default, per-layer views, My-priorities view with presets and sliders, confidence
rendering, inspector with sources, URL state; `/methodology` from manifest; `/about`.

**v2.** Scenario and horizon toggles; place search via bundled admin1 list; compare-two-places
panel; population-weighted flood exposure; OSM-derived transit (ODbL); LGBTQ policy layers once
permissions land; drought (JRC GDO) and wildfire (GWIS); GEM seismic as labeled non-climate;
embeddable iframe.

**Later.** Downloadable hex data with attribution bundle; plain-language place summaries
(clearly labeled); time-slider across horizons.

| Session | Mode | Lang | Scope | Kickoff prompt |
|---|---|---|---|---|
| 0 | Plan | - | Read spec, ask §13, plan S1 | Done 2026-09-20 |
| 1 | acceptEdits | Python | Repo layout, `sources.yaml`, `dimensions.yaml`, `fetch` with checksums, `grid`, `pop`, `admin`, joiners, fixtures, tests, CI, README | Done 2026-09-20 |
| 2 | acceptEdits | Python | Aqueduct riverine + coastal to hexes | Done 2026-09-22 (direct mirror, §13.19; Dhaka / Reykjavik checked) |
| 3 | acceptEdits | Python | CCKP heat + Aqueduct water stress | Done 2026-09-22 (Phoenix / Sahel checked) |
| 4 | acceptEdits | Python | Wellbeing, composites, manifest, res 5 | Done 2026-09-22 at res 4; SHDI waits on Saj's download (WHR fallback runs); res 5 run pending |
| 4b | acceptEdits | Python | Global life dimensions | Done 2026-09-22 (GSAP, OECD via TL2 crosswalk §13.21, ILOSTAT) |
| 4c | acceptEdits | Python | US life dimensions | Done 2026-09-22 (ACS with B09019 §13.20, EPA SLD, Urban/NCES, HRSA); MEDSL waits on the guestbook or a manual download (§13.26) |
| 5 | acceptEdits | Python + shell | Tiles and publish | Done 2026-09-22 (python tiler §13.18, publish local/r2, smoke page); R2 upload waits on credentials |
| 6 | acceptEdits | TypeScript | Map app | Done 2026-09-22 (verified in a browser on the fixture build) |
| 7 | acceptEdits | TypeScript | Inspector, priorities, methodology, deploy | Built 2026-09-22; Cloudflare Pages deploy waits on credentials (`web/scripts/deploy.mjs`, `docs/deploy.md`) |

## 17. Acceptance criteria (v1)

- [x] `python -m pipeline all` runs from a clean clone (with `data/raw/` populated) to
  `hexes.pmtiles` and `manifest.json` with one command, and re-running does no work when inputs
  are unchanged. (res 4, 2026-09-22; every stage is cached by input fingerprint)
- [x] `python -m pipeline --fixtures all` runs every implemented stage on the fixture world in
  under a minute and is exercised by CI. (Session 1, 2026-09-20)
- [x] Every inhabited hex has `coverage` in 0 to 4, `wb_res` in {admin1, national, none}, and
  `bivar` in 0 to 9; the §8.5 percentages are printed and recorded on `/methodology`. (tests +
  manifest `coverage_summary`, 2026-09-22)
- [x] All four §8.5 spot checks land in plausible classes, with the reason in the manifest notes.
  (§15 row "8.5 spot checks", manifest `spot_checks`, 2026-09-22)
- [x] No hex anywhere has a hazard or dimension score of 0 because of missing data; missing
  renders as `_ok = false` or `_res = none` and is visibly different on the map. (tests
  `test_no_score_is_zero_because_of_missing_data`, tiles drop missing attributes, grey + hatch
  styling verified in the browser, 2026-09-22)
- [ ] The map loads at zoom 2 in under 3 seconds on broadband with tiles served from R2, and no
  request goes to any third party other than R2 and the basemap provider.
- [x] Clicking any land hex opens the inspector with raw values, scores, flags, wellbeing with
  source and resolution badge, coverage count, life dimensions with resolution badges, and a
  sources list matching the manifest. (fixture build in the browser, 2026-09-22)
- [x] The bivariate legend, the per-layer ramps, the confidence key and the coverage chips are
  present and match what is drawn. (2026-09-22)
- [x] Moving a priorities slider or picking a preset recolors the map client-side without a
  network request, and dimensions missing on a hex drop out of the composite. (measured in the
  browser on the res-4 build, 2026-09-22: a slider change added no tile or data requests;
  `expressions.test.ts` covers the denominator rule)
- [x] Reloading a URL restores the same view, preset, weights and toggles. (`url.test.ts` round
  trips; observed in the browser, 2026-09-22)
- [x] `/methodology` lists every source with license, vintage and processing note, states the
  scenario, horizon, percentile-rank rationale, the §12 resolution decision, the non-commercial
  statement, and known gaps by region and dimension. (rendered from the manifest, 2026-09-22)
- [x] No paid, scrape-restricted or unlicensed data appears anywhere in the repo, tiles or manifest.
  (`sources.yaml` review, `publish` refuses unconfirmed sources, 2026-09-22)
- [x] `/about` says clearly that the map does not recommend where to live. (2026-09-22)

## 18. Prior art (for the README and /about)

Researched 2026-09-20. Nothing combines global future-climate projections with subnational
wellbeing and user-chosen weights on open data.

| Tool | What it has | What it lacks for this goal |
|---|---|---|
| FEMA National Risk Index, NOAA CMRA, US Climate Vulnerability Index, ND-GAIN Urban Adaptation | tract-level hazard, some future projections, social vulnerability | US only; framed as "who needs help", no user weighting; federal tools are politically fragile (CMRA archived 2026) |
| Probable Futures, Climate Impact Explorer, Climate Impact Lab | global future climate by warming level | hazard only, no wellbeing, no weighting |
| WRI Aqueduct | global flood and water hazard, future scenarios | hazard only, researcher-facing |
| Movemap, Dwellics (US), WhereNext (global) | user-weighted livability filters | present-day or historical climate only |
| INFORM Risk, WorldRiskIndex | global composite risk | national resolution, no wellbeing |
| EIU Liveability, Numbeo, Nomad List | city wellbeing | cities only, no projections, proprietary or restricted terms |
| World Happiness Report, Subnational HDI, OECD Regional Well-Being | wellbeing at national / admin1 | no climate, no map |
| AlphaGeo (Climate Alpha) | global hazards fused with socioeconomics | proprietary, enterprise-priced, no consumer weighting |
| Climate Central, Maplecroft, First Street, ClimateCheck | fine-grained hazard | proprietary, not open, US-centric |
| Teleport, ProPublica/Rhodium map, FEMA Future Risk Index, Zillow climate scores | closest historical analogues | dead, frozen, deleted or withdrawn |

Open-source references worth studying: WFP PRISM (hazard x vulnerability map), GFDRR CCDR-tools
(bivariate hazard x poverty), CLIMADA, global-healthy-liveable-cities/global-indicators.

## 19. Relationship to CivicRadar patterns

Reuse: R2 client conventions, plain-English error mapping, no-tracker privacy posture,
README-with-ASCII-diagram habit, GitHub Actions only for lightweight jobs. Do not reuse: the Redis
cache layer or any per-request API pattern; this app is static-first by invariant 5.

## 20. Life dimensions

### 20.1 Why

Different stages and shapes of life weigh different things: an early-career renter cares about
jobs, transit and rent; a family about schools; a queer person about legal protection and
community; some people want a mixed-income neighborhood or a majority-Black one. The map lets a
person say which of these matter and see the result, without the pipeline deciding what "good"
means for dimensions where there is no universal answer.

### 20.2 The dimension registry (`pipeline/dimensions.yaml`)

Everything a person can weight is a dimension. Hazards and wellbeing are dimensions too, which
keeps the scoring and the UI uniform.

```yaml
- id: jobs                 # short; ships in every tile
  name: Job market
  group: life              # hazard | wellbeing | life
  kind: score              # score | signed | composition
  higher_is: better        # score only: better | worse
  coverage: [global, oecd, us]
  sources: [ilostat_youth_unemp, oecd_reg_unemp, acs_b23001]
  joiners:
    - {source: acs_b23001, joiner: area_weighted_overlay, res: tract, field: unemp_16_29}
    - {source: oecd_reg_unemp, joiner: polygon_centroid, res: admin1, field: youth_unemp}
    - {source: ilostat_youth_unemp, joiner: iso_lookup, res: national, field: value}
```

Three kinds:

- `score`: a 0-100 percentile within the dimension's coverage domain (§20.4). Direction is
  fixed by `higher_is`. The person weights it.
- `signed`: a lean stored as `{id}_lean` in -100..100 (political two-party margin). The client
  turns it into a match against what the person picks (left, right, competitive).
- `composition`: integer percent shares (`race_w`, `race_b`, `race_h`, `race_a`, `race_o`) plus
  `race_maj`. The client lets the person pick a target group or "diverse" and computes a match.
  Never scored server-side (invariant 8).

Joiners run in priority order; the first that yields a value sets `{id}_raw` and `{id}_res`.
A national fallback is applied only when the registry lists it, and the tag says `national`.

### 20.3 Joiners (`pipeline/joiners/`)

| Joiner | Input | Used for |
|---|---|---|
| `polygon_centroid` | hex centroid in polygon, pick a field | SHDI admin1, GSAP admin1, OECD TL2, US county, Aqueduct water stress |
| `iso_lookup` | `iso_a2` to a national table | WHR, ILOSTAT, V-Dem |
| `area_weighted_overlay` | small polygons to hex, weighted by overlap area x polygon population density | ACS tracts, EPA SLD block groups, school districts |
| `point_density` | points per hex, optionally per 10k residents | transit stops |
| `raster_mean` | mean of a raster's valid pixels inside the hex (tag `hex`); `decimate` block-averages very fine rasters first, `sample: centroid` point-samples rasters coarser than the hex | travel time to healthcare (1 km), PM2.5 (0.01°), tree cover (100 m, decimate 10), burned area (0.25°, centroid) |
| `point_mean` | weighted mean of point values inside the hex (tag `hex`) | Ookla speed tiles at their centroids, weighted by tests |

All six are idempotent and bbox-aware. The pop stage's GHSL sums are the population weights so
joins agree with `population`.

### 20.4 Scoring within a coverage domain

A `score` dimension's percentile is computed over inhabited hexes that have a value at the same
resolution class: global dims over the world, US dims over the US. The domain is recorded in the
manifest so `/methodology` can say "US jobs score: percentile among inhabited US hexes". Never
percentile a US-only value against the world.

### 20.5 The My-priorities view

Client-side composite: `sum(w_i * match_i * has_i) / sum(w_i * has_i)` as a MapLibre
expression, where `match_i` is the score (or the derived match for signed and composition
dims) and `has_i` is 1 when the hex has that dimension. Missing dimensions leave the
denominator (invariant 3). Presets are named weight sets in `web/src/presets.ts`:

| Preset | Emphasis |
|---|---|
| Early career | jobs, transit, housing cost, low exposure |
| Raising kids | schools, low exposure, housing, healthcare |
| Queer and looking for community | LGBTQ+ protection and presence, politics (left lean), jobs |
| Retiring | healthcare, heat, low exposure, wellbeing |
| Climate first | four hazards only |

Each life dimension in the panel shows a coverage chip (Global / OECD / US only) and greys out
where the hovered or clicked hex has `_res = none`.

### 20.6 Sources by dimension (researched 2026-09-20, status search; see §15)

| id | Dimension | Global source (res) | US source (res) | License notes |
|---|---|---|---|---|
| jobs | Youth / early-career job market | ILOSTAT youth unemployment CC BY 4.0 (national); OECD regional labour (TL2), Eurostat `lfst_r_lfu3rt` (NUTS2) | ACS B23001 age 16-29 unemployment (tract); BLS LAUS (county, all ages) | All open. ACS is public domain; pull the Summary File at build time. |
| transit | Public transit access | Mobility Database catalog CC0 + OSM ODbL (points) - v2 | EPA Smart Location Database v3 transit frequency `D4C` and walkability (block group), public domain | OSM per-hex derivatives are a derivative database under ODbL; keep tiles-only or license that layer ODbL. Walk Score and AllTransit excluded. |
| school | School quality | GDL SHDI education sub-index (admin1; attainment, not quality) | Urban Institute Education Data Portal ODC-BY (district); NCES CCD boundaries public domain | SEDA is best but non-transferable; ask Stanford. PISA is CC BY-NC-SA (national). GreatSchools excluded. |
| lgbtq | LGBTQ+ protection and presence | Equaldex / ILGA are non-commercial, national; Rainbow Europe unlicensed - v2 pending permission | ACS B11009 same-sex couple households per 1k households (tract, PD, proxy); MAP state policy tally (state, permission needed) | Hardest to ship open. Ship the ACS proxy first, clearly labeled. |
| pol | Political lean (signed) | none subnational; V-Dem CC BY-SA (national) is a different construct, v2 | MIT Election Lab county presidential returns 2000-2024 (county, CC0 expected) | Cook PVI excluded. Verify MEDSL license block on the DOI. |
| race | Racial / ethnic composition | none comparable; most countries do not collect it | ACS B03002 (tract) or 2020 DHC P2 (block), public domain | NHGIS and IPUMS excluded (no redistribution). Differential-privacy noise is negligible at hex scale. |
| incmix | Income mix / inequality | World Bank GSAP poverty headcount CC BY 4.0 (admin1, 168 economies, 2023) as level; OECD regional Gini (TL2) | ACS B19001 bracket entropy + B19083 Gini (tract) | Global gives between-region level, US gives within-area diversity; labeled as different constructs. |
| house | Housing cost burden | OECD Regional Well-Being housing (TL2) | ACS B25071 rent as share of income (tract); HUD FMR (county) | Zillow usable only with on-page attribution; deferred. |
| health | Healthcare access | OECD Regional Well-Being health (TL2); Eurostat `hlth_rs_prsrg` (NUTS2) | HRSA Area Health Resources File physicians per 10k (county) | All open. |
| cost | Cost of living (price level) | World Bank ICP 2021 household price level CC BY 4.0 (national, World = 100); WDI GDP price level rescaled to it where ICP has no row | BEA Regional Price Parities 2024, metro area then state (US = 100), public domain | Numbeo (proprietary) |
| rent | Housing cost (rent level) | OECD / Eurostat rent levels - v2 | HUD Fair Market Rent, 2-bedroom, FY2026 (county / FMR area), public domain, manual download (§13.30) | Zillow ZORI (terms forbid redistribution) |
| care | Travel time to healthcare | Malaria Atlas Project motorized travel time 2019, 1 km, CC BY 4.0 (`hex`) | same | - |
| net | Internet speed | Ookla Open Data 2026 Q2 fixed, then mobile, CC BY-NC-SA 4.0 (`hex`) | same | - |
| air | Air quality (PM2.5), group `env` | WashU ACAG SatPM2.5 V6.GL.03 2024, 0.01°, CC BY 4.0 (`hex`) | same | - |
| trees | Tree cover, group `env` | Copernicus Global Land Cover 100 m tree-cover fraction 2019, CC BY 4.0 (`hex`, block-averaged to 1 km) | same | ESA WorldCover 10 m (too large for the laptop) |
| fire | Wildfire (burned area), group `env` | GFED5 burned area 2001-2020 mean, 0.25°, CC BY 4.0 (`hex`, centroid) | same | GWIS country profiles (no download) |
| drought | Drought risk, group `env` | Aqueduct 4.0 baseline `drr_cat` 0-4 (Aqueduct 3.0 lineage), CC BY 4.0 (`basin`) | same | JRC GDO SPI-12 kept as a fallback (1°, CC BY 4.0) |

Design rule from this table: three dimensions (lgbtq, pol, race) have no global answer. The UI
greys them out outside the US instead of substituting a country-level proxy.
