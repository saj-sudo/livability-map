# Cost of living, rents and six extra layers — implementation plan

> For agentic workers: one task per agent, TDD, commit per task, follow `CLAUDE.md` and `SPEC.md`
> (§6.1 naming, §20.2 registry, invariant 3: missing is never 0, invariant 4: no `VERIFY` sources).

**Goal:** add two cost-of-living dimensions (`cost`, `rent`) now, then six extra layers
(healthcare travel time, air quality, tree cover, internet speed, wildfire, drought) once their
sources are verified, plus SHDI sub-indices when the SHDI file arrives.

**Conventions that already exist (reuse, do not reinvent):**
- `pipeline/prep/<source>.py` exposes `load(settings, source, sources) -> DataFrame | GeoDataFrame`
  with the columns named in `pipeline/dimensions.yaml`; register in `pipeline/prep/__init__.py`
  `LOADERS` and bump `PREP_VERSION`. `prep.util` has `read_xlsx`, `find_column`, `iso3_to_iso2`,
  `country_to_iso2`; `rawfiles.resolve_vector/resolve_raster` open zips.
- `pipeline/sources.yaml`: one entry per download (`access: direct`, `verified: confirmed` only
  after a first-hand check, `geometry:` for the polygon source of a tabular source, `member:` for
  a file inside a zip, `sheet:`/`header_row:` for xlsx). `tests/test_registry.py` enforces that
  polygon joiners have geometry.
- `pipeline/dimensions.yaml`: `kind: score`, `higher_is`, `coverage`, `sources`, ordered `joiners`
  (`source, joiner, res, field, domain, label, weight_field`). Joiners: `polygon_centroid`,
  `iso_lookup`, `area_weighted_overlay`, `point_density`.
- Fixture world `pipeline/fixtures/make_fixtures.py` (bump `VERSION`) + `pipeline/fixtures/sources.yaml`
  map every real source id to a synthetic file carrying the final column names; `tests/test_dims.py`
  asserts per-hex results on fixtures.
- Web: `web/src/lib/dims.ts` (`DIM_ORDER` append-only, `FALLBACK` list), `web/src/lib/inspect.ts`
  (`fmtLife` keyed on the resolution tag), `web/src/presets.ts`; tests in `web/src/lib/*.test.ts`.

## Task 1: `cost` (price level) and `rent` (housing cost level)

Verified 2026-09-22:
- BEA RPP state: `https://apps.bea.gov/regional/zip/SARPP.zip` (39 KB) -> `SARPP_STATE_2008_2024.csv`,
  header `GeoFIPS,GeoName,Region,TableName,LineCode,IndustryClassification,Description,Unit,2008..2024`;
  `GeoFIPS` is quoted and space-padded (`" 01000"` = state FIPS + `000`); LineCode 1 = "RPPs: All
  items", US = 100; four footer lines to drop. Metro: `https://apps.bea.gov/regional/zip/MARPP.zip`
  (146 KB) -> `MARPP_MSA_2008_2024.csv`, `GeoFIPS` = 5-digit CBSA code. No county table exists.
  Vintage: 2024 statistics, released 2026-02-19. License: US federal work (public domain).
- Polygons: Census cartographic CBSA `https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_cbsa_500k.zip`
  (key `GEOID` = CBSA code) and states `https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip`
  (key `GEOID` = 2-digit state FIPS). Verify both with a HEAD request before use; if 2025 is
  missing use GENZ2024.
- World Bank ICP 2021 household-consumption price level (World = 100):
  `https://api.worldbank.org/v2/sources/90/Country/all/Series/9100000/Classification/PX.WL/Time/all/data?format=json&per_page=20000`
  (verify the `all` country selector works; otherwise page through `v2/sources/90/country`).
  Fallback WDI GDP price level: `https://api.worldbank.org/v2/en/indicator/PA.NUS.PPPC.RF?downloadformat=csv`
  (zip; CSV header on line 5: `Country Name,Country Code,Indicator Name,Indicator Code,1960..2026`;
  ISO3 = `Country Code`; drop aggregates using `Metadata_Country_*.csv` rows with blank `Region`;
  latest broad year 2024). Both CC BY 4.0.
- HUD FMR FY2026: `https://www.huduser.gov/portal/datasets/fmr/fmr2026/FY26_FMRs.xlsx` (GET, HEAD
  returns 202); columns to verify on file (historically `fips`/`fips2010`, `state`, `county`,
  `countyname`, `metro`, `fmr_0..fmr_4`); use the 2-bedroom rent. Public domain. Join to
  `cb_counties` on the 5-digit county FIPS (first 5 of the 10-digit fips).

Registry:
```yaml
- id: cost
  name: Cost of living (price level)
  group: life
  kind: score
  higher_is: worse
  coverage: [global, us]
  sources: [bea_rpp_metro, bea_rpp_state, cb_cbsa, cb_states, wb_icp_pli, wb_gdp_pli]
  joiners:
    - {source: bea_rpp_metro, joiner: polygon_centroid, res: county, field: rpp_all, domain: us, label: bea}
    - {source: bea_rpp_state, joiner: polygon_centroid, res: admin1, field: rpp_all, domain: us, label: bea}
    - {source: wb_icp_pli, joiner: iso_lookup, res: national, field: pli_household, domain: global, label: icp}
    - {source: wb_gdp_pli, joiner: iso_lookup, res: national, field: pli_gdp, domain: global, label: wdi}
  note: "US: BEA regional price parity, all items (US = 100). Elsewhere: World Bank ICP 2021 household-consumption price level (World = 100), GDP price level where ICP has no row. Different bases, labeled"
- id: rent
  name: Housing cost (rent level)
  group: life
  kind: score
  higher_is: worse
  coverage: [us]
  sources: [hud_fmr, cb_counties]
  joiners:
    - {source: hud_fmr, joiner: polygon_centroid, res: county, field: fmr_2br, domain: us, label: hud}
  note: "HUD Fair Market Rent for a 2-bedroom unit, FY2026, USD per month; the OECD/EU rent level is v2"
```
Prep loaders: `prep/bea.py` (`load_metro`, `load_state` -> GeoDataFrame with `rpp_all` for the
latest year, joined to the CBSA/state polygons; the `bea_rpp_*` sources carry `geometry: cb_cbsa`
/ `cb_states`), `prep/icp.py` (`load_household` latest year per ISO3 -> `iso_a2, pli_household, year`;
`load_gdp` -> `iso_a2, pli_gdp, year`), `prep/hud.py` (`fmr_2br` by county).
Fixtures: `counties.gpkg` gains `fmr_2br` and `rpp_all`; `adm1.gpkg`-derived `states.gpkg` stand-in
for BEA state with `rpp_all`; `icp.csv` with `iso_a2, pli_household` (XA only) and `gdp_pli.csv`
with `iso_a2, pli_gdp` (both), so the fallback path is exercised.
Web: add `cost`, `rent` to `DIM_ORDER` (append) and `FALLBACK`; `fmtLife` formats `cost` as
"index 112 (US = 100)" for `county`/`admin1` tags and "index 143 (world = 100)" for `national`,
`rent` as "$1,450/month (2-bedroom FMR)"; presets: `early` gets `cost: 2, rent: 2`, `retiring`
gets `cost: 2`. Tests: `tests/test_prep_loaders.py` (BEA GeoFIPS parsing, WDI preamble/aggregate
filtering, ICP latest-year pick, HUD fips slicing), `tests/test_dims.py` (fixture: XB hexes get
`rent_res == county`, `cost_res == county` inside the fixture metro / `admin1` elsewhere in XB,
XA hexes `cost_res == national` with `cost_lbl == icp`), web tests updated.

## Task 2: verify the six extra sources (research only) -> table in this file

For each: exact URL, size, format, CRS/resolution, key/variable, license text, vintage.
1. Healthcare travel time: Malaria Atlas Project "accessibility to healthcare 2020" (motorized,
   1 km, CC BY 4.0) — a global GeoTIFF; a walking variant exists too.
2. Air quality: van Donkelaar V5GL (annual PM2.5 ~0.01 degree global NetCDF/GeoTIFF, CC BY 4.0),
   latest year; the WashU/Dalhousie download path.
3. Tree cover: a global fraction layer under ~3 GB (Copernicus Global Land Cover 100 m
   "tree-cover fraction" 2019, CC BY 4.0) rather than 10 m WorldCover.
4. Internet speed: Ookla open data (CC BY-NC 4.0) on AWS S3 `ookla-open-data`, latest quarter,
   fixed and mobile, parquet with quadkey tiles, `avg_d_kbps`, `tests`.
5. Wildfire: a static global fire-danger or burned-area layer (GWIS/JRC or Copernicus) with an
   open license; note GADM-based admin statistics if rasters are not open.
6. Drought: JRC GDO or a global drought-frequency raster with an open license.

## Task 3+: implement the extras (one task per source, after Task 2)

- Raster sources need a `raster_mean` / `raster_frac` joiner in `pipeline/joiners/` driven by
  `dimensions.yaml` (`joiner: raster_mean`, `source:` a raster source, `res: hex`), using
  `h3util.aggregate_raster`; `hex` is a new `RES_TAGS` entry (SPEC §6.1 change: hex-resolution
  dimensions carry the tag `hex`). Ookla needs a `point_mean` joiner (weighted mean of point
  values per hex).
- Wildfire and drought join the `hazards` stage: make `HAZARDS` registry-driven (dimensions.yaml
  hazard entries gain `method: centroid | frac_above | polygon | mean`, `raw:` column, `unit:`),
  `coverage` counts all hazards, the UI shows "N of M hazard layers" and hatches `coverage < M`
  (M from the manifest). Update SPEC §6.1, §8.4, §9.3 in the same change.
- SHDI sub-indices (`shdi_health`, `shdi_edu`, `shdi_income`) reuse `prep/shdi.py` once the file
  is present.
