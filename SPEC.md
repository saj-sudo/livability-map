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
| Property-level or street-level resolution (v1) | H3 hexes at tens of km in v1. Roadmap (§16, decided 2026-09-22): neighbourhood hexes in cities (Session 8), then property-level *readouts* of the physical layers under a clicked point (Session 10) and block-level hexes inside urban centres (Session 11). Socioeconomic layers never go below the block group, and nothing is scored per property: a per-property score built on race or income is steering. |
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
   `grid` (a statistical grid such as the Eurostat 1 km census grid, aggregated per hex),
   `basin` (a hydrological sub-basin polygon at the centroid), `admin1`, `county`, `tract`,
   `area` (a small statistical area outside the US: England LSOA; later IRIS, DAs, SA2),
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
8. **Not every dimension has a "better".** Composition dimensions (§20.2) are never ranked by the
   pipeline and never weighted by the person: they are shown per place as context (§13.39).

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
  - WRI Aqueduct 4.0 future water stress   - OECD Regional Well-Being (TL2), ILOSTAT (nat.)   - JRC GHSL GHS-SMOD 1 km (urban)
                                           - US: Census ACS, MEDSL, EPA SLD, Urban Inst., HRSA
                                           - EU: Eurostat 1 km census grid; England: IoD 2025 (LSOA)
                                           - hex-level: MAP travel time, ACAG PM2.5, tree cover, Ookla
        |                                          |                                                |
        v                                          v                                                v
  +--------------------------------------------------------------------------------------------------------+
  |               pipeline/  (Python CLI:  python -m pipeline [--fixtures] [--res 6] [--bbox ...] <stage>)  |
  |                                                                                                        |
  |  fetch     download + sha256 each source per pipeline/sources.yaml -> data/raw/<id>/                  |
  |            manual sources (GEE export, registration) are checked for presence, recipe printed         |
  |  urban     GHS-SMOD classes -> urban centre / cluster polygons with ids -> data/interim/urban.parquet |
  |  grid      resolution plan (pipeline/resolution_plan.yaml, §9.1): res 4 + 5 from Natural Earth land,  |
  |            res 6 = children of res-5 cells in US/EU/UK/EFTA or touching urban clusters, res 7 =       |
  |            children inside urban centres -> data/interim/hexes_r{res}.parquet (one per resolution)   |
  |  pop       GHSL 1 km -> sum per hex -> population, inhabited flag (pop >= POP_MIN)                    |
  |  admin     hex centroid -> geoBoundaries admin0/admin1 -> iso_a2, admin1_id, admin1_name              |
  |  hazards   for each raster: windowed read of the hexes' cells -> aggregate per hex (§8.1)            |
  |            -> per-hazard 0-100 percentile score + *_ok flag (res 6/7 ranked against res 5, §13.32)    |
  |  dims      prep/<source>.py turns each raw source into a joinable layer; for each dimension in       |
  |            dimensions.yaml run its joiners (§20.3): polygon_centroid | iso_lookup |                   |
  |            area_weighted_overlay | point_density | raster_mean | point_mean                          |
  |            -> {id}_raw, {id}_res (hex|grid|basin|admin1|county|tract|area|national|none)             |
  |  score     exposure = mean(available hazard scores), coverage = count(*_ok)                           |
  |            {id}_score = percentile within the dimension's coverage domain (§8.2, §20.4)               |
  |            wb_score, bivar class 1-9 (§8.4); res 6/7 use res-5 distributions (§13.32)                |
  |  export    data/out/hexes_r{res}.parquet (+ ref on refined parents) + manifest.json with the plan    |
  |  tiles     python tiler (tippecanoe optional), one archive per plan archive, zooms from the manifest: |
  |            hexes.pmtiles (hex4 z2-4, slim at z2; hex5 z5-7, overzoomed) + hexes_nbhd.pmtiles (hex6     |
  |            z8-9) + hexes_city.pmtiles (hex7 z10-11), where built (§9.1, §13.18, §13.33)               |
  |  validate  archives match the manifest and are fresh; no hazard / dimension came out empty;           |
  |            no coverage drop > 5% against the live build (§13.38); publish runs it again               |
  |  publish   local: every archive + manifest.json -> web/public/data. r2 (boto3, .env): real            |
  |            whole-world builds only; archives under content-addressed keys (immutable),                |
  |            range + CORS check, then manifest.json switched last (§13.24, §13.38)                      |
  +-----------------------------------------------+--------------------------------------------------------+
                                                  |  static files only
                                                  v
  +----------------------------------------+    range      +------------------------------------------+
  |  web/  Next.js 16 static export        | <--requests-- |  Cloudflare R2 (public, custom domain)   |
  |  on Cloudflare Pages                   |               |  <archive>.<sha12>.pmtiles (immutable)   |
  |  MapLibre GL JS v6 + pmtiles protocol  |               |  manifest.json (no-cache, switched last) |
  |  one source per archive; refined       |               |  (basemap: OpenFreeMap, §13.5)           |
  |  parents (ref) hidden under finer hexes|               +------------------------------------------+
  |  views: bivariate | per hazard |       |
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

### 6.1 Hex record (one row per H3 cell, every resolution in the plan)

```
h3            string   H3 index (hex string)
res           int      4-7 today (any 4-10 the resolution plan lists, §9.1)
ref           bool     true when a finer layer replaced this cell (absent otherwise; §9.1)
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
  "dimensions": [ { "...each dimensions.yaml entry with coverage counts by _res; every joiner carries unit, multiply and decimals so the inspector can print a raw value it has never seen (2026-09-22)..." : "" } ],
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

The resolutions, where each is built, its zooms and its archive live in
`pipeline/resolution_plan.yaml` (Session 8, §13.32); nothing else hard-codes a resolution.

| Layer | H3 res (avg cell) | Built where | Zooms | Archive |
|---|---|---|---|---|
| hex4 | 4 (1,770 km²) | all land | z2-4 (slim attributes at z2) | hexes.pmtiles |
| hex5 | 5 (253 km²) | all land | z5-7, overzoomed beyond | hexes.pmtiles |
| hex6 | 6 (36 km²) | children of res-5 cells whose centroid is in the US, EU-27, UK or EFTA, or that touch a GHS-SMOD urban cluster | z8-9, overzoomed | hexes_nbhd.pmtiles |
| hex7 | 7 (5.2 km²) | children of res-6 cells that touch a GHS-SMOD urban centre | z10-11, overzoomed | hexes_city.pmtiles |

`land` entries are complete (every land cell); `children` entries exist only where a rule matched
and drop children whose centre is in the ocean. A layer keeps drawing past its last zoom unless
the next finer present layer is complete, so res 5 still covers the world at z8+; each cell a
finer layer replaced carries `ref = true` and is hidden from that layer's first zoom, so colours
never double up. Along the edge of a refined region the H3 children do not tile their parents
exactly (H3 is not perfectly nested), which leaves a hairline of basemap or overlap there.
Adding a tier is a yaml entry: Session 11 appends res 9/10 inside urban centres at z14-16 with
its own archive. Zoom 0-1 is not built because a res-4 hex is under two pixels there and the
world tile would exceed 5 MB.

### 9.2 Tile build

Built by `pipeline/tiler.py` (pure Python: `mapbox-vector-tile` + the `pmtiles` writer, decision
§13.18) with one layer per resolution and one archive per plan `archive` (§9.1): `hex4` for zoom
2-4 (the slim attribute set at zoom 2, where a res-4 hex is about two pixels) and `hex5` for zoom
5-7 in `hexes.pmtiles`, `hex6` z8-9 in `hexes_nbhd.pmtiles` and `hex7` z10-11 in `hexes_city.pmtiles`
(a layer drawn past its last zoom must close its archive: MapLibre overzooms per source); MapLibre overzooms
beyond each layer's last zoom without further requests. Zooms come from the manifest, never a
table in code. Each archive stays under ~300 MB (§14.10); past that, split by plan `archive`. tippecanoe (felt fork) remains an optional backend when it is on PATH
(`tiles --backend tippecanoe` after `export --geojson`). Upload to R2; CORS per §15.14; the web
app reads the PMTiles via HTTP range requests.

### 9.3 Styling rules (MapLibre style spec, data-driven)

- Default layer: `bivar` classes 1 to 9 with a red/blue bivariate palette (Joshua Stevens'
  scheme: exposure warms from grey to red across the columns, wellbeing cools from grey to teal
  up the rows, both high is a dark mauve); class 0 neutral grey. The dark theme uses a grid
  derived in OKLCH so lightness climbs with exposure + wellbeing (`web/scripts/bivar_dark.mjs`).
  Both grids are checked with the dataviz validator: every row and column lightness-monotone,
  corner cells separable under protan/deutan simulation. Palettes live in `web/src/lib/palette.ts`,
  one per theme.
- Per-hazard and per-dimension layers: `*_score` single-hue sequential ramp (rust for hazards,
  teal for wellbeing, green for life dimensions, blue-violet for the priorities match);
  `*_ok = false` or `*_res = 'none'` in grey.
- Confidence: `coverage < 4` gets a hatch `fill-pattern` overlay (§13.4); `wb_res = 'national'`
  a faint dashed outline (it covers whole countries while SHDI is absent, so it must read as a
  texture, not an error); `wb_res = 'none'` grey on wellbeing views.
- Hex seams are drawn in the paper tone at low alpha so the mesh recedes; the hovered hex gets a
  thin ink outline and the selected hex a haloed ink outline, both driven by feature-state.
- `inhabited = false` hidden by default, toggle to show (§13.8).
- Legend is a 3x3 bivariate grid with axis labels "more climate exposure" and "higher
  wellbeing", corner captions in words, and the hovered hex's cell lit, plus a confidence key,
  a no-data key and, in the priorities view, a coverage chip per dimension. Chips come from the
  manifest's scoring domains (`domains`), never from the per-resolution coverage counts.

### 9.4 Basemap

OpenFreeMap (free vector tiles, no key, no signup). Style `positron` for the light theme and
`dark` for the dark theme; the theme follows the system preference, can be toggled in the header,
and is remembered in localStorage only (never a URL parameter, so a shared link never forces a
theme). A theme change calls `setStyle(url, { transformStyle })` so the hex source and layers
survive without a tile refetch. Attribution "OpenFreeMap © OpenMapTiles Data from OpenStreetMap"
comes from the style itself. One-person service with no SLA; if it goes away, the fallback is a
Protomaps basemap PMTiles extract self-hosted on R2. Never Mapbox, never ArcGIS.

## 10. Web app surfaces

- `/`: full-screen map under a slim header (wordmark, place search, nav, "How to read this map",
  theme toggle). Left panel: view selector (Bivariate | Heat | Riverine flood | Coastal flood |
  Water stress | Wellbeing | My priorities), presets as chips and a 0-5 slider with a readout per
  dimension visible only in My priorities (dimensions grouped by the manifest `group`, so new
  ones appear without code; a dimension with no hex data in the build is disabled and says so),
  scenario and horizon as a static line, confidence toggle, inhabited toggle, legend.
- Place search: an accessible combobox over a bundled gazetteer (`web/public/gazetteer.json`:
  Natural Earth 1:10m populated places with POP_MAX >= 50k or a capital, plus geoBoundaries ADM1
  names; built by `web/scripts/build_gazetteer.py`), fetched lazily from the same origin on first
  focus. Ranking: exact > prefix > word-prefix > substring, cities before regions, then
  population. Picking a place flies the map (zoom 6 city, 5 region) and selects the hex under the
  point once the map is idle. No request leaves the origin (invariant 7).
- Hover (pointer devices only): a small readout beside the pointer with the place, population
  and one line for the current view (bivariate class in words, a layer's score with its raw
  value, or the priorities match with how many weighted dimensions are missing here); the legend
  lights the matching cell. Slim low-zoom tiles carry no names, so the title says to zoom in.
- Inspector (click a hex): country and admin1 name, population, a one-sentence plain-language
  summary (what the colour means, hazard layers present, national wellbeing fallback, priorities
  match with what is missing), the person's weighted priorities as thin bars (a missing
  dimension is a hatched "no data here" row), each hazard's raw value and score with its `_ok`
  state, wellbeing value with source and resolution in words, coverage "3 of 4 hazard layers",
  bivariate class in words, each life dimension's value and resolution (or "no data here"), one
  "Sources" disclosure listing the manifest entries, and "Compare with another place". The
  numbers in the bars come from `web/src/lib/chart.ts`, a TypeScript twin of the §20.5
  expression, tested against the real expression so what is read equals what is drawn.
- Compare two places: after "Compare with another place", the next click or search landing
  fills a second slot and a side-by-side table replaces the inspector; a dot marks the better
  side on a row only when both sides have data and the dimension has a direction. Session-only,
  not in the URL.
- First visit: a three-step intro card (what the colours mean, make it yours, every number has a
  source); dismissal is one localStorage flag, reopenable from the header. No cookies.
- Phones (under 640px): the panels live in one bottom sheet with Layers and Place tabs and three
  snaps (peek, half, full); selecting a hex opens Place at half. Methodology and About links sit
  at the bottom of the Layers tab because the header hides the nav there.
- URL state: `?lat=&lng=&z=&view=&preset=&w=<csv weights>&conf=&inh=` so any view is
  shareable. No server state. Theme and intro flags are localStorage, not URL.
- `/methodology`: generated from `manifest.json` at build time.
- `/about`: what this is and is not (§3 in plain language), including "does not recommend
  where to live", the non-commercial statement, and what the browser stores and fetches.

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
- Res-5 global run, 2026-09-22: grid 11 s, pop 214 s, admin 8 s, hazards 1,814 s / 1.7 GB,
  dims 6,376 s / 7.3 GB for the first ten dimensions (transit 2,553 s, race 1,506 s, school
  1,080 s: the US tract and block-group overlays), then 917 s / 3.0 GB for the eight added
  dimensions via `dims --only` (tree cover 564 s, travel time 154 s, PM2.5 156 s). 570,143 land
  hexes; 93.5% of inhabited hexes have all four hazards. Tiles for both resolutions (18
  dimensions, 82 attributes): 10,984 tiles, 2.32 million features, 145.7 MB in 932 s on the
  memory-capped pool; largest tile z3/4/3 at 670 KB gzipped. The first res-5 tile build had
  died with `BrokenProcessPool` (§15).
- `dims --only <id> [--only <id> ...]` recomputes the named dimensions and merges them into the
  existing `dims_r{res}.parquet`; use it to add a layer, and run without it when a prepared
  layer or the registry changed for a dimension you did not name.
- Neighbourhood resolution (Session 8, 2026-09-23 run): urban 39 s / 1.2 GB; grid res 6 + 7
  512 s / 1.8 GB -> 963,098 res-6 cells (670,216 inhabited) and 401,729 res-7 cells (357,504
  inhabited), over twice the first estimate because GHS-SMOD class 21 (peri-urban) is widespread;
  pop 122 s, admin 15 s, hazards 1,609 s / 2.9 GB (cell-set aggregation reads only windows the cells
  touch); dims res 6 14,553 s and res 7 4,931 s, peak 7.9 GB (US tract overlays dominate); the three
  refreshed dimensions at res 4 + 5 via `dims --only` 795 s; score 13 s, export 28 s. Tiles:
  hexes.pmtiles 146.5 MB (10,984 tiles), hexes_nbhd.pmtiles 206.2 MB (30,430 tiles, 952 s),
  hexes_city.pmtiles 254.3 MB (128,730 tiles, 705 s). hex7 at z10-13 made a 531 MB archive (z13
  alone 276 MB), so hex7 was tiled z10-12; after the five NGO dimensions (15 more attributes,
  2026-09-23) it reached 306 MB and is now tiled z10-11 (a res-7 hex is ~30 px wide at z11) and
  overzoomed. hexes.pmtiles grew from 148 to 191 MB and hexes_nbhd from 207 to 264 MB.
- Country sources (2026-09-23): `dims --only jobs --only incmix --only house --only rent` at res
  4-7 took 7,862 s / 5.7 GB (the StatCan profile is streamed once from its 2.25 GB zip into
  `interim/prep/`), then score 14 s, export 30 s, tiles 2,778 s: hexes 148.1 MB, hexes_nbhd
  207.3 MB, hexes_city 255.8 MB. Share of inhabited res-6 hexes carrying the country value: DE
  rent 99%; NL rent 93%, incmix 90%; FR jobs 99%, incmix 18% (Filosofi covers communes of 5,000+
  only); CA jobs / incmix / house 98%; AU jobs / house / rent 100%.
- Each tile archive stays under ~300 MB; the plan's `archive` field splits layers across files
  when one would pass that (§14.10).
- Releases (§13.38): `validate` checks a build without uploading; `publish --target r2` validates
  against the live manifest, uploads content-addressed archives and switches `manifest.json`
  last; `npm run deploy` builds the site against that live manifest. Old archives stay in the
  bucket (about 0.7 GB per release), so earlier Pages builds keep working; prune by hand when
  a release is long retired.

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
2. **H3 resolutions:** 4 + 5 everywhere; 6 and 7 where the resolution plan says (§9.1, §13.32).
3. **Scenario and horizon:** moderate pathway (RCP4.5 for Aqueduct, SSP2-4.5 for CCKP), 2050.
4. **Confidence rendering:** hatch pattern.
5. **Basemap:** OpenFreeMap.
6. **GEM seismic in v1:** no; v2 as a labeled non-climate layer.
7. **PostGIS:** no; geopandas only.
8. **Hide uninhabited hexes by default:** yes, with toggle.
9. **POP_MIN / DEPTH_MIN:** 100 people / 0.15 m.
10. **Visual identity:** new system (CivicRadar not available in the build environment). Built in
    Session 9 (2026-09-22) as "Atlas": a reference-atlas feel rather than a dashboard. Tokens are
    CSS variables (`--paper`, `--panel`, `--ink`, `--muted`, `--rule`, `--accent`, `--nodata`) in
    `web/src/app/globals.css`, exposed to Tailwind via `@theme inline`, with a full dark set;
    Newsreader (serif) for the wordmark, place names, headings and summaries, Source Sans 3 with
    tabular figures for controls and numbers, both self-hosted from `@fontsource-variable`
    packages; one 6px radius, hairlines rather than nested cards, no all-caps labels; the
    bivariate legend is the hero element (§9.3). Motion only answers an action (sheet snap,
    legend highlight) and respects `prefers-reduced-motion`.
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
31. **Urban mask** (Saj, 2026-09-22): GHS-SMOD R2023A epoch 2025 at 30 arc-seconds, the same grid as
    GHS-POP, not the 1.7 GB GHS-UCDB. The `urban` stage polygonises class 30 (urban centre) and
    classes >= 21 (urban cluster) into `data/interim/urban.parquet` with `uc_id`, `kind` and
    `area_km2`, the saved layer Session 11 reuses for block hexes. Epoch 2025: 12,195 urban centres
    and 226,941 urban clusters; only pieces touching a raster window edge are unioned, on a
    sub-pixel precision grid so seams close (a single global union ran for over half an hour).
32. **Resolution plan and reference scoring** (Saj, 2026-09-22): `pipeline/resolution_plan.yaml`
    replaces the flat resolution list (§9.1). Res 6 covers the US, EU-27, UK and EFTA plus every
    urban cluster, res 7 every urban centre. A derived resolution is ranked against the inhabited
    hexes of the finest complete resolution (res 5) in the same domain, including the wellbeing
    min-max bounds and the bivariate tercile cuts, so a neighbourhood keeps its colour meaning at
    every zoom; its score reads "better than X% of inhabited res-5 hexes".
33. **One archive per derived layer, and refined parents** (2026-09-22): tiles are built per plan archive
    (`hexes.pmtiles`, `hexes_nbhd.pmtiles`, `hexes_city.pmtiles`): MapLibre overzooms per source, so a
    derived layer drawn past its zooms must be the last layer of its archive, and smaller archives
    stay under the §14.10 size guard. The web
    app adds one source per archive. `export` writes `ref = true` on cells a finer layer
    replaced; the coarse layer fades those cells out from the finer layer's first zoom.
34. **Neighbourhood statistics and tags** (Saj, 2026-09-22): the Eurostat 2021 1 km census grid
    (employment rate of 15-64s, tag `grid`, domain `eu`) and the English Indices of Deprivation
    2025 on LSOA 2021 (employment, health and housing-barrier domains, tag `area`, domain `uk`)
    ship in this session; German Zensus, Dutch CBS, French IRIS, Canadian DAs and Australian SA2
    ship after Session 8 (§13.35). Germany, France, Switzerland and Latvia publish no usable
    employment count on the grid (EMP -9999 in over half their populated cells), so their grid
    employment is treated as missing and those hexes fall back to OECD / ILOSTAT. A joiner may declare `higher_is` opposite to its dimension (IoD
    deprivation feeding `jobs`); the score stage reflects that joiner's percentile so every
    `{id}_score` obeys the dimension's direction, and the raw value ships as published.
35. **Country small areas and grids** (2026-09-23, after Session 8): Germany (Zensus 2022 average
    net cold rent per m², 100 m grid -> `rent`), the Netherlands (CBS 2023 squares: average WOZ home
    value at 100 m -> `rent`, low-income household share at 500 m -> `incmix`; CBS publishes income
    only at 500 m), France (INSEE RP 2021 employment and Filosofi 2021 poverty rate per IRIS on IGN
    Contours...IRIS 2023 -> `jobs`, `incmix`), Canada (StatCan 2021 Census Profile per DA:
    employment rate, LIM-AT low income, households spending 30%+ on shelter -> `jobs`, `incmix`,
    `house`) and Australia (ABS 2021 GCP per SA2: employment-to-population, median rent, median rent
    over median household income -> `jobs`, `rent`, `house`). Grids carry tag `grid`, small areas
    `area`; each country is its own scoring domain (`de`, `nl`, `fr`, `ca`, `au`). StatCan's
    tenant-only 30%+ rate is not used: it reads 0 in most small DAs where the owner-plus-tenant rate
    does not (randomly rounded counts), so the all-households rate is used instead. ABS publishes
    unavailable values as 0, which the loader treats as missing. Canada and Australia are **not**
    added to the res-6 country list: 86% of Canadians and 90% of Australians already live under
    res-6 cells through the urban-cluster rule, and adding both countries whole would add ~470k
    mostly empty cells; their data applies at every resolution anyway. The cluster rule stays at
    GHS-SMOD class >= 21: dense-only variants cut res 6 by only 8-18% (900k / 803k cells) while
    dropping the peri-urban neighbourhoods of 180-530 million people (measured 2026-09-23).
36. **NGO hex layers** (2026-09-23): three open datasets from research groups fill gaps outside
    the US, Europe, Canada and Australia, each a new `life` dimension at tag `hex`: travel time to
    the nearest city of 50,000+ (`city`, Malaria Atlas Project 2015, CC BY 3.0 / 4.0), relative
    wealth within the country (`wealth`, Meta Relative Wealth Index 2021, 93 low- and
    middle-income countries, CC BY-NC 4.0) and organised-violence deaths per year within 25 km
    (`conflict`, UCDP GED 26.1, 2016-2025, CC BY 4.0). A new joiner, `point_radius`, takes the
    mean or sum of point values within a radius of the hex centre (never smaller than the hex
    edge), because the wealth tiles (~2.4 km) are sparser than res-7 hexes and conflict needs a
    neighbourhood, not a cell. `domain_by_country` ranks a joiner's values only against hexes of
    the same country (`{id}_dom` = `country:<ISO2>`), since the wealth index is relative within
    each country. For `conflict`, 0 is a real value (no recorded event within 25 km; the event
    set is global); events placed only at an admin1 or country centroid are excluded so they do
    not create hotspots. OPHI's subnational MPI was evaluated and not added: its survey regions
    match the map's admin1 polygons for only 70% of regions (Tanzania, Uganda and Rwanda among
    the structural mismatches), and World Bank GSAP already covers the same ground. Sources that
    need a login, a key or permission are listed in `docs/manual-steps.md`.
37. **Walking time to care, water points, presets** (2026-09-23): `walkcare` is MAP's walking-only
    travel time to the nearest hospital or clinic (2020, CC BY 3.0), beside the motorised `care`,
    because many people in Sub-Saharan Africa have no motorised transport. `water` is the share of
    WPdx+ community water points within 5 km that had water at the last visit (19 countries, incl.
    all of East Africa); it is missing where no point is recorded, since WPdx covers community
    points and a city on piped water has few. WPdx's global export states no user licence; the
    data is recorded as CC BY-SA 4.0, as WPdx publishes it on HDX, with the derived attributes
    labelled share-alike (confirmation requested in docs/manual-steps.md). The presets use the new
    layers where they fit: Early career weights `city`, Raising kids `conflict` and `water`,
    Retiring `walkcare`.
38. **Release safety** (2026-10-18, before the first R2 publish): a build reaches the live map
    only through checks, and a release can be rolled back.
    - *Code in the cache key.* Every stage fingerprint carries a digest of the stage module and
      every `pipeline` module it imports (transitively, including the lazily registered prep
      loaders), taken over the syntax tree without docstrings: a comment never rebuilds, a
      changed expression always does. `--force` is no longer needed after a code change. The
      first run after this change rebuilds everything once.
    - *Per-dimension freshness.* `dims` fingerprints each dimension (its sources' raw files, its
      registry entry, the resolution's hexes / pop / admin, the code) and a plain run recomputes
      only the stale ones; `--only` forces the named ones and never marks the others fresh.
    - *Fetch keeps the verified file.* A re-download whose checksum differs from CHECKSUMS is
      parked as `<file>.new` and reported; the verified file stays. A hand-placed (manual)
      file that differs from last time is accepted but announced.
    - *`validate` stage* between `tiles` and `publish` (and run again inside `publish`):
      archives match the manifest's bytes and sha256 and are fresh for their parquet and code;
      every hazard and every life dimension reaches an inhabited hex at the land resolutions
      (a dimension whose sources are all missing downloads is a warning, since the web app
      disables it); against the live build, no resolution, hazard or dimension loses more than
      5% of its inhabited coverage (`--max-drop` for an explained drop) and none disappears.
    - *R2 release order.* Fixture, `--bbox` and partial builds never go to R2 (`auto` resolves
      to `local` for them). Archives upload as `<archive>.<sha12>.pmtiles` with
      `immutable` caching, are never overwritten, and are skipped when already present; the
      first one is range- and CORS-checked; only then is `manifest.json` (`no-cache`) switched,
      with a dated copy under `manifests/`. `npm run deploy` builds against that live manifest
      (never a local one), refuses fixture, bbox, local or plain-keyed manifests and archives the
      bucket does not serve, and keeps `public/data` out of the Pages upload. Tiles and app
      change together; rollback is redeploying an earlier Pages build, whose archives are still
      in the bucket.
39. **Racial composition is context, never a priority** (Saj, 2026-10-19): the priorities view
    used to let a person pick a group ("majority Black", "diverse", ...) and colour tracts by how
    well their composition matched. That is sorting neighbourhoods by who lives there, the
    steering §3 and §16 rule out at every scale, not only per property. Composition dimensions
    now have no slider and no part in the composite (`weightable()` in `web/src/lib/dims.ts`);
    old links that weight `race` or carry `race=` are read without it. The place panel still
    shows the tract's shares with their source, because knowing a place's demographics is
    legitimate context; ranking or filtering by them is not. Political lean stays weightable
    (not a protected class), labelled US-only as before.

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
| 2026-09-22 | 14.8 Natural Earth populated places | **confirmed** by download through `python -m pipeline fetch --only natural_earth_places`: `ne_10m_populated_places.zip` (2.8 MB, sha256 in `data/raw/CHECKSUMS`), public domain, fields NAME, ISO_A2, POP_MAX, FEATURECLA; used only for the web app's search index (§10), never joined to a hex. | https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places.zip |
| 2026-09-22 | 14.9 Basemap dark style | **confirmed** in the browser: `https://tiles.openfreemap.org/styles/dark` loads with the same sprite/glyph hosts; `setStyle` with `transformStyle` keeps the hex source and six layers with no PMTiles refetch. | https://tiles.openfreemap.org/styles/dark |
| 2026-09-22 | Session 8: GHS-SMOD R2023A | **confirmed** by download (`python -m pipeline fetch --only ghsl_smod`): 34.0 MB zip with `GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss_V2_0.tif` (43202 x 21384 int16, 30 arc-second EPSG:4326, nodata -200, classes 10 water, 11-13 rural, 21-23 urban cluster, 30 urban centre; same grid as GHS-POP), `.clr`, `.ovr` and the GHSL Data Package 2023 PDF; CC BY 4.0 (JRC GHSL). | https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_SMOD_GLOBE_R2023A/GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss/V2-0/ |
| 2026-09-22 | Session 8: Eurostat Census 2021 grid V3 | **confirmed** by download: 566 MB zip (`Eurostat_Census-GRID_2021_V3.zip`, 2026-05-30) with CSV (340 MB), parquet (76 MB, used), GeoPackage (1.3 GB), GeoTIFF, per-country CSVs, SDMX metadata and `read.me`. 4,595,932 1 km cells in ETRS89-LAEA (EPSG:3035), `GRD_ID` = `CRS3035RES1000mN{y}E{x}`, columns T, M, F, Y_LT15, Y_1564, Y_GE65, EMP, NAT, EU_OTH, OTH, SAME, CHG_IN, CHG_OUT, LAND_SURFACE, POPULATED, CNTR_ID; -8888 = confidential, -9999 = not available (EMP is -9999 for whole countries); EU-27 + CH, NO, LI (no IS; FR without overseas regions). Copyright European Union: reuse authorised with source indicated and modifications stated (Decision 2011/833/EU). | https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip |
| 2026-09-22 | Session 8: English Indices of Deprivation 2025, File 7 | **confirmed** by download: 9.9 MB CSV, 33,755 LSOA 2021 rows, 56 columns; used: `LSOA code (2021)`, `Index of Multiple Deprivation (IMD) Score`, `Income Score (rate)`, `Employment Score (rate)`, `Health Deprivation and Disability Score`, `Barriers to Housing and Services Score`, `Total population: mid 2022`, `Working age population 18-66 (for use with Employment Deprivation Domain): mid 2022`. Published 2025-10-30 by MHCLG under the Open Government Licence v3.0. England only. | https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025 |
| 2026-09-22 | Session 8: ONS LSOA (December 2021) Boundaries EW BGC V5 | **confirmed** by download through the Open Geography hub download API (302 to a cached GeoJSON on services1.arcgis.com; feature service `Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5`, 35,672 features): 66 MB GeoJSON in EPSG:27700 with LSOA21CD, LSOA21NM, LSOA21NMW, BNG_E, BNG_N, LAT, LONG. Licence per https://www.ons.gov.uk/methodology/geography/licences: Open Government Licence v3.0, "Contains OS data © Crown copyright and database right 2021". | https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/68515293204e43ca8ab56fa13ae8a547/geojson?layers=0 |
| 2026-09-23 | Zensus 2022 rent grid (DE) | **confirmed** by download: `Durchschnittliche_Nettokaltmiete_und_Anzahl_der_Wohnungen.zip` (11.0 MB, Destatis, version 2 of 2025-07-08); 100 m CSV (73 MB, `;`, decimal comma, UTF-8) with GITTER_ID_100m, x_mp_100m / y_mp_100m (cell centre, EPSG:3035), durchschnMieteQM (EUR/m² net cold rent), AnzahlWohnungen, werterlaeuternde_Zeichen (KLAMMERN = uncertain); 1,287,342 cells, 1.00-49.69, median 6.41; empty or secret cells are absent. Licence dl-de/by-2-0 (Datensatzbeschreibung), © Statistische Ämter des Bundes und der Länder. | https://www.zensus2022.de/DE/Ergebnisse-des-Zensus/gitterzellen.html |
| 2026-09-23 | CBS vierkantstatistieken 2023 (NL) | **confirmed** by download: `2026-cbs_vk100_2023_vol.zip` (75.5 MB; gpkg layer cbs_vk100_2023, EPSG:28992, 390,396 squares, 131 columns) and `2026-cbs_vk500_2023_vol.zip` (19.4 MB; cbs_vk500_2023, 151,108 squares). Used: gemiddelde_woz_waarde_woning (thousand EUR), aantal_woningen; percentage_laag_inkomen_huishouden (only at 500 m; 16,260 squares), aantal_part_huishoudens. Sentinels -99997 (0-4 / secret / absent) and -99995 (later version). Licence CC BY 4.0 (CBS copyright page; product description asks for '© CBS'). | https://www.cbs.nl/nl-nl/dossier/nederland-regionaal/geografische-data/kaart-van-100-meter-bij-100-meter-met-statistieken |
| 2026-09-23 | INSEE IRIS 2021 + IGN Contours IRIS 2023 (FR) | **confirmed** by download: `base-ic-activite-residents-2021_csv.zip` (39.5 MB; 49,280 IRIS; `;`, decimal point; P21_POP1564, P21_ACTOCC1564; updated 2025-12-16), `BASE_TD_FILO_IRIS_2021_DISP_CSV.zip` (0.9 MB; 16,026 IRIS of communes with 5,000+ inhabitants; `;`, decimal comma; DISP_TP6021 poverty rate; ns / nd / s / so), and IGN `CONTOURS-IRIS_3-0__SHP__FRA_2023-01-01.7z` (34.2 MB; nine shapefiles in territory CRSs, 49,424 IRIS, CODE_IRIS). Every INSEE code matches the 2023 contours. Filosofi 2022 was not published at IRIS level. Licence Ouverte 2.0 (Etalab), 'Source : Insee'; IGN metadata: licence ouverte Etalab. | https://www.insee.fr/fr/statistiques/8268843 , https://www.insee.fr/fr/statistiques/8229323 , https://data.geopf.fr/telechargement/resource/CONTOURS-IRIS |
| 2026-09-23 | StatCan 2021 Census Profile DA + boundaries (CA) | **confirmed** by download: 98-401-X2021006 (GetFile.cfm GEONO=006; 2.25 GB zip, six cp1252 CSVs ~26.6 GB, long format, 2,631 characteristics, 57,936 DAs; HEAD answers 302 -> 404, GET works). Used ids 1, 2223, 2229 (employment rate), 345 (LIM-AT %), 1465 / 1467 (all households, 30%+ on shelter). Suppression by blank + symbol (x, .., ..., F). Boundaries `lda_000b21a_e.zip` (197 MB, EPSG:3347, 57,932 DAs, DGUID matches). Statistics Canada Open Licence ('Adapted from Statistics Canada ...'). | https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/download-telecharger.cfm?Lang=E |
| 2026-09-23 | ABS 2021 GCP DataPack SA2 + ASGS SA2 boundaries (AU) | **confirmed** by download: `2021_GCP_SA2_for_AUS_short-header.zip` (42.3 MB, Release 2; 2,472 rows per table; G01 Tot_P_P, G02 Median_rent_weekly / Median_tot_hhd_inc_weekly, G43 P_15_yrs_over_P / Percnt_Employment_to_populn_P; unavailable published as 0; pseudo-SA2s ending 97979799 / 99999499) and `SA2_2021_AUST_SHP_GDA2020.zip` (50.7 MB, EPSG:7844, 2,473 SA2, 19 without geometry, SA2_CODE21 matches). CC BY 4.0, 'Based on Australian Bureau of Statistics data'. | https://www.abs.gov.au/census/find-census-data/datapacks |
| 2026-09-23 | MAP travel time to cities 2015 | **confirmed** by download via WCS (coverage `Accessibility__201501_Global_Travel_Time_to_Cities`, AccessConstraints NONE): 3.03 GB int32 GeoTIFF, 43200 x 17400, EPSG:4326, nodata -9999, minutes 0-41556. MAP open-access policy: CC BY 3.0 with citation; the Earth Engine catalog lists CC BY 4.0. The same policy page also answers the licence of `map_healthcare`. | https://malariaatlas.org/open-access-policy/ |
| 2026-09-23 | Meta Relative Wealth Index (HDX) | **confirmed** by download: combined 93-country CSV with quadkeys (122 MB, 2,463,901 zoom-14 tiles; latitude / longitude = tile centre, rwi, error; no country column). HDX licence field quotes CC BY-NC 4.0 with the PNAS 2022 citation. Per-country files (110) also checked: the Moldova and North Macedonia resources have swapped URLs, and IND+PAK is one file; the combined file is used, ranked per hex country. | https://data.humdata.org/dataset/relative-wealth-index |
| 2026-09-23 | UCDP GED 26.1 | **confirmed** by download: `ged261-csv.zip` (39 MB, `GEDEvent_v26_1.csv`, 417,968 events 1989-2025, 49 columns incl. latitude, longitude, best, year, where_prec 1-7 per the codebook). Licence on the downloads page: CC BY 4.0, cite Davies, Pettersson & Öberg (2026) and Sundberg & Melander (2013). | https://ucdp.uu.se/downloads/ |
| 2026-09-23 | OPHI global MPI 2025 subnational (not used) | **confirmed** by download (`subnational-results-mpi.xlsx`, 1,359 regions in 101 countries; OPHI FAQ: CC BY 4.0, HDX: CC0). Name match to geoBoundaries ADM1 only 70% (survey regions differ from admin1); not added, §13.36. | https://data.humdata.org/dataset/global-mpi |
| 2026-09-23 | MAP walking-only travel time to healthcare 2020 | **confirmed** by download via WCS (`Accessibility__202001_Global_Walking_Only_Travel_Time_To_Healthcare`): 3.03 GB float32 GeoTIFF, nodata -9999, minutes 0-138,745 (median 798 over land pixels). CC BY 3.0 per the MAP open-access policy (no layer exceptions); Earth Engine lists CC BY 4.0. | https://malariaatlas.org/open-access-policy/ |
| 2026-09-23 | WPdx+ water points | **confirmed** by download (Socrata `eqje-vguj`, 544 MB CSV, 440,270 points, 19 countries, HXL `#` column prefixes; status_id Yes 318,821 / No 92,531 / Unknown 28,918; is_duplicate on 25,640). Licence: no user licence on the export; WPdx's HDX country sets say CC BY-SA; providers license to WPdx under CC BY 4.0. Recorded as CC BY-SA 4.0 pending WPdx's confirmation. | https://data.waterpointdata.org/dataset/eqje-vguj |

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

**Finer resolution (decided 2026-09-22).** Three tiers, physical layers first:

- *Session 8, neighbourhood:* H3 res 7 inside urban footprints (GHSL urban centres), res 6 across
  the US and Europe, res 5 elsewhere; statistical grids (Eurostat 1 km, UK LSOA, German and
  Dutch 100 m, French IRIS, Canadian DAs, Australian SA2). The `urban` mask and the resolution
  plan are designed to be reused by the two tiers below.
- *Session 10, point readouts:* property-level evidence without property-level hexes. The
  finest rasters (FEMA NFHL and EA flood zones, Copernicus DEM 30 m with a sea-level bathtub,
  Landsat land-surface temperature, WorldCover 10 m or Meta canopy height 1 m, EU and BTS
  noise maps, SILVIS WUI) are published as cloud-optimized GeoTIFFs on R2 and the web app reads
  the pixel under a click with range requests (geotiff.js), the same way it reads PMTiles.
  No server (invariant 5), no score at that level, only values with sources. US and EU first
  (storage: ~100 GB per global 10 m layer).
- *Session 11, block hexes:* res 9 or 10 inside urban centres, physical layers and distances
  only (walking time to transit stops from GTFS, parks, groceries, clinics via a self-hosted
  OSM router; ODbL makes the derived table share-alike, a licence decision like Ookla's), one
  region at a time as its own PMTiles archive with a size cap in §11. New tags `block` and
  `street`, zoom plan z14-16. Needs a build machine bigger than the laptop for whole countries.

Never per property: census counts below the block group, racial composition, income, politics.
The Fair Housing Act and its EU equivalents are the reason, not just taste.

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
| 8 | acceptEdits | Python (+ web layer list) | Neighbourhood resolution: `urban` mask, resolution plan in `grid`, hex6/hex7 tiles, statistical grids by country | Built 2026-09-22 (PR `claude/neighborhood`): urban stage, resolution plan, reference scoring, two archives, Eurostat grid and England IoD 2025; Zensus, CBS, IRIS, DAs and SA2 remain (§13.34); plan in docs/superpowers/plans/2026-09-22-session-8-neighbourhood-resolution.md |
| 10 | acceptEdits | Python + TypeScript | Point readouts: COGs on R2 for the physical layers, geotiff.js reads under a click, "what is here" panel | Planned after Session 8 (see "Finer resolution" above) |
| 11 | acceptEdits | Python | Block hexes (res 9/10) inside urban centres, physical layers and OSM/GTFS distances, per-region archives | Planned after Session 10; needs a larger build machine |
| 9 | acceptEdits | TypeScript (+ one gazetteer script) | Visual identity, search, hover, inspector summary and bars, compare, intro, phone sheet | Built 2026-09-22 on `claude/design` (§13.10 "Atlas", §9.3 palette, §10 surfaces); Session 8 (neighbourhood resolution) is still outlined only, in `docs/superpowers/plans/` on the cost/rent branch |

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
- [x] With the site served locally, every request the browser makes goes to the same origin
  (page, fonts, tiles, gazetteer) or to the basemap provider; nothing else. Search, hover, the
  inspector bars, compare, the intro and the phone sheet never show a missing value as zero.
  (Playwright network audit and browser checks on the res-4 build, Session 9, 2026-09-22; the
  R2 half of the zoom-2 load-time criterion above is still open)

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
  `race_maj`. Shown in the place panel as shares; never scored, never weighted, never matched
  against a group the person picks (§13.39).
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
| `raster_mean` | mean of a raster's valid pixels inside the hex (tag `hex`; the block-average factor is capped per resolution so a res-7 hex still spans a few pixels); `decimate` block-averages very fine rasters first, `sample: centroid` point-samples rasters coarser than the hex | travel time to healthcare (1 km), PM2.5 (0.01°), tree cover (100 m, decimate 10), burned area (0.25°, centroid) |
| `point_mean` | weighted mean of point values inside the hex (tag `hex`, or `grid` for statistical grid cells) | Ookla speed tiles at their centroids, weighted by tests; Eurostat 1 km census cells at their centres, weighted by 15-64 population |
| `point_radius` | mean or sum of point values within a radius of the hex centre (tag `hex`; radius never below the hex edge; `domain_by_country` ranks within each country) | Meta Relative Wealth Index tiles (mean, 3 km), UCDP conflict deaths (sum, 25 km) |

All seven are idempotent and bbox-aware. The pop stage's GHSL sums are the population weights so
joins agree with `population`.

### 20.4 Scoring within a coverage domain

A `score` dimension's percentile is computed over inhabited hexes that have a value at the same
resolution class: global dims over the world, US dims over the US. The domain is recorded in the
manifest so `/methodology` can say "US jobs score: percentile among inhabited US hexes". Never
percentile a US-only value against the world.

### 20.5 The My-priorities view

Client-side composite: `sum(w_i * match_i * has_i) / sum(w_i * has_i)` as a MapLibre
expression, where `match_i` is the score (or the derived match for the signed dimension;
composition dimensions are never weighted, §13.39) and `has_i` is 1 when the hex has that dimension. Missing dimensions leave the
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
| jobs | Youth / early-career job market | ILOSTAT youth unemployment CC BY 4.0 (national); OECD regional labour (TL2); EU: Eurostat 2021 1 km census grid employment rate of 15-64s (`grid`, Session 8); England: IoD 2025 employment deprivation (LSOA, `area`); France: INSEE RP 2021 employment rate 15-64 (IRIS, `area`); Canada: StatCan 2021 employment rate (DA, `area`); Australia: ABS 2021 employment-to-population (SA2, `area`) | ACS B23001 age 16-29 unemployment (tract); BLS LAUS (county, all ages) | All open. ACS is public domain; pull the Summary File at build time. |
| transit | Public transit access | Mobility Database catalog CC0 + OSM ODbL (points) - v2 | EPA Smart Location Database v3 transit frequency `D4C` and walkability (block group), public domain | OSM per-hex derivatives are a derivative database under ODbL; keep tiles-only or license that layer ODbL. Walk Score and AllTransit excluded. |
| school | School quality | GDL SHDI education sub-index (admin1; attainment, not quality) | Urban Institute Education Data Portal ODC-BY (district); NCES CCD boundaries public domain | SEDA is best but non-transferable; ask Stanford. PISA is CC BY-NC-SA (national). GreatSchools excluded. |
| lgbtq | LGBTQ+ protection and presence | Equaldex / ILGA are non-commercial, national; Rainbow Europe unlicensed - v2 pending permission | ACS B11009 same-sex couple households per 1k households (tract, PD, proxy); MAP state policy tally (state, permission needed) | Hardest to ship open. Ship the ACS proxy first, clearly labeled. |
| pol | Political lean (signed) | none subnational; V-Dem CC BY-SA (national) is a different construct, v2 | MIT Election Lab county presidential returns 2000-2024 (county, CC0 expected) | Cook PVI excluded. Verify MEDSL license block on the DOI. |
| race | Racial / ethnic composition | none comparable; most countries do not collect it | ACS B03002 (tract) or 2020 DHC P2 (block), public domain | NHGIS and IPUMS excluded (no redistribution). Differential-privacy noise is negligible at hex scale. |
| incmix | Income mix / inequality | World Bank GSAP poverty headcount CC BY 4.0 (admin1, 168 economies, 2023) as level; OECD regional Gini (TL2); France: Filosofi 2021 poverty rate (IRIS); Netherlands: CBS low-income household share (500 m, `grid`); Canada: LIM-AT low income (DA) | ACS B19001 bracket entropy + B19083 Gini (tract) | Global gives between-region level, US gives within-area diversity; labeled as different constructs. |
| house | Housing cost burden | OECD Regional Well-Being housing (TL2); England: IoD 2025 barriers to housing and services (LSOA, `area`); Canada: households spending 30%+ of income on shelter (DA); Australia: median rent / median household income (SA2) | ACS B25071 rent as share of income (tract); HUD FMR (county) | Zillow usable only with on-page attribution; deferred. |
| health | Healthcare access | OECD Regional Well-Being health (TL2); Eurostat `hlth_rs_prsrg` (NUTS2); England: IoD 2025 health deprivation and disability (LSOA, `area`) | HRSA Area Health Resources File physicians per 10k (county) | All open. |
| cost | Cost of living (price level) | World Bank ICP 2021 household price level CC BY 4.0 (national, World = 100); WDI GDP price level rescaled to it where ICP has no row | BEA Regional Price Parities 2024, metro area then state (US = 100), public domain | Numbeo (proprietary) |
| rent | Housing cost (rent level) | OECD / Eurostat rent levels - v2; Germany: Zensus 2022 net cold rent per m² (100 m, `grid`); Netherlands: CBS average WOZ home value (100 m); Australia: ABS median weekly rent (SA2) | HUD Fair Market Rent, 2-bedroom, FY2026 (county / FMR area), public domain, manual download (§13.30) | Zillow ZORI (terms forbid redistribution) |
| care | Travel time to healthcare | Malaria Atlas Project motorized travel time 2019, 1 km, CC BY 4.0 (`hex`) | same | - |
| city | Access to a city | Malaria Atlas Project travel time to the nearest city of 50,000+, 2015, CC BY 3.0 (`hex`) | same | a proxy for access to jobs and services, not the job market |
| wealth | Relative wealth within the country | Meta Relative Wealth Index 2021, 93 LMICs, CC BY-NC 4.0 (`hex`, ranked within each country) | - | relative, never compared across countries |
| conflict | Armed conflict nearby | UCDP GED 26.1 deaths per year within 25 km, 2016-2025, CC BY 4.0 (`hex`) | same | ACLED excluded (no redistribution) |
| walkcare | Walking time to healthcare | MAP walking-only travel time to the nearest facility, 2020, CC BY 3.0 (`hex`) | same | the motorised time is `care` |
| water | Working water points nearby | WPdx+ share of water points within 5 km with water, 19 countries, CC BY-SA 4.0 (`hex`) | - | missing where no point is recorded |
| net | Internet speed | Ookla Open Data 2026 Q2 fixed, then mobile, CC BY-NC-SA 4.0 (`hex`) | same | - |
| air | Air quality (PM2.5), group `env` | WashU ACAG SatPM2.5 V6.GL.03 2024, 0.01°, CC BY 4.0 (`hex`) | same | - |
| trees | Tree cover, group `env` | Copernicus Global Land Cover 100 m tree-cover fraction 2019, CC BY 4.0 (`hex`, block-averaged to 1 km) | same | ESA WorldCover 10 m (too large for the laptop) |
| fire | Wildfire (burned area), group `env` | GFED5 burned area 2001-2020 mean, 0.25°, CC BY 4.0 (`hex`, centroid) | same | GWIS country profiles (no download) |
| drought | Drought risk, group `env` | Aqueduct 4.0 baseline `drr_cat` 0-4 (Aqueduct 3.0 lineage), CC BY 4.0 (`basin`) | same | JRC GDO SPI-12 kept as a fallback (1°, CC BY 4.0) |

Design rule from this table: three dimensions (lgbtq, pol, race) have no global answer. The UI
greys them out outside the US instead of substituting a country-level proxy.
