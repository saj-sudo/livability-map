# Session 8: Neighbourhood Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (native, recommended: the tasks share the `Settings.plan` / `ResEntry` interfaces and the real-data runs happen on this laptop) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build H3 res 6 across the US and Europe and res 7 inside GHSL urban centres, tiled at z8-13 beside the existing global res 4/5 archive, with two neighbourhood-scale socioeconomic sources (Eurostat 1 km census grid 2021, English Indices of Deprivation 2025), without a global res-7 archive.

**Architecture:** A new `urban` stage vectorises GHS-SMOD classes into a saved polygon layer with ids. A resolution plan file (`pipeline/resolution_plan.yaml`) replaces the flat `H3_RES` list: complete resolutions are filled from land as today, derived resolutions are the H3 children of parent cells that match a rule (country list, urban kind). Every later stage keeps writing one parquet per resolution; hazards and score percentile derived resolutions against the finest complete resolution so a hex's colour means the same thing at every zoom. Export writes the plan and a `ref` flag (parent was refined) into the manifest and tiles; the tiler builds one PMTiles archive per plan `archive` from the manifest's zoom ranges; the web app reads layers, sources and overzoom flags from the manifest and hides refined parents where a finer layer takes over.

**Tech Stack:** Python 3.11+ (h3 v4, rasterio, shapely 2, geopandas, pandas, pmtiles, mapbox-vector-tile), Next.js 16 + MapLibre GL v6 + vitest, uv, pytest, ruff.

**Spec:** the "Design" section below (plan mode allowed only this file to be written; Task 0 copies the design to `docs/superpowers/specs/2026-09-22-neighbourhood-resolution-design.md` and this plan to `docs/superpowers/plans/2026-09-22-session-8-neighbourhood-resolution.md`).

## Context

SPEC §16 "Finer resolution" (decided 2026-09-22) makes Session 8 the first of three tiers: neighbourhood hexes now, point readouts (Session 10) and block hexes (Session 11) later. Today `settings.res` is a flat list, every stage loops it, tiles zooms come from a fixed table (`tiles.LAYER_ZOOMS`), scores are percentiles within one resolution, and the web layer stack has no gap handling. Saj's decisions in this session's brainstorm: GHS-SMOD R2023A as the urban mask (not UCDB), reference-distribution scoring for derived resolutions, Eurostat grid + England IMD in this PR (the other five country sources as follow-ups), res 6 across US + EU27 + UK + EFTA.

## Design

### D1. Resolution plan (`pipeline/resolution_plan.yaml`, SPEC §9.1)

```yaml
# One entry per H3 resolution, ascending. `land` entries cover every land cell (complete);
# `children` entries are the H3 children of parent cells that match any `where` rule.
resolutions:
  - {res: 4, fill: land, zooms: [2, 4], archive: hexes, slim_below_zoom: 3}
  - {res: 5, fill: land, zooms: [5, 7], archive: hexes}
  - res: 6
    fill: children
    parent: 5
    where:
      countries: [US, GB, IS, NO, CH, LI, AT, BE, BG, HR, CY, CZ, DK, EE, FI, FR, DE, GR, HU, IE, IT, LV, LT, LU, MT, NL, PL, PT, RO, SK, SI, ES, SE]
      urban: cluster        # any parent whose polygon intersects a GHS-SMOD class >= 21 polygon
    zooms: [8, 9]
    archive: hexes_fine
  - res: 7
    fill: children
    parent: 6
    where: {urban: centre}  # GHS-SMOD class 30
    zooms: [10, 13]
    archive: hexes_fine
```

Rules: `res` strictly increasing within 4..10; first entry `land`; `children` needs an earlier `parent`; zoom ranges ascending and non-overlapping; `archive` matches `^[a-z][a-z0-9_]*$`; `where` keys ⊆ {countries, urban}; `urban` ∈ {centre, cluster}. Any res 4-10 works without code changes (Session 11 adds `{res: 9, fill: children, parent: 7, where: {urban: centre}, zooms: [14, 16], archive: <region>}`). `--res` selects a subset of plan resolutions; default is all of them. Fixture runs use `pipeline/fixtures/resolution_plan.yaml` (countries `[XA]`, same zooms).

### D2. `urban` stage (SPEC §5, between `fetch` and `grid`)

Reads `ghsl_smod` (GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss_V2_0, 30 arc-second EPSG:4326, the same grid as GHS-POP; classes 30 urban centre, 23/22/21 urban cluster, 13/12/11 rural, 10 water, nodata -200). For `centre` (class == 30) and `cluster` (class >= 21) it polygonises each window with `rasterio.features.shapes`, unions pieces across windows, explodes, and writes `data/interim/urban.parquet` (GeoParquet: `uc_id` int ordinal by area within kind, `kind`, `area_km2` in EPSG:6933, geometry EPSG:4326). This is the saved mask Session 11 reuses. `ghsl_smod` joins `REFERENCE_SOURCE_IDS` so `publish` checks it.

### D3. `grid` stage with the plan

`land` entries: unchanged (`build_hexes`). `children` entries: parents = `hexes_r{parent}.parquet`; `countries` rule via `polygon_centroid(parents, adm0, "shapeGroup")` + `iso3_to_iso2`; `urban` rule via `gpd.sjoin(parent polygons, urban[kind], predicate="intersects")`; children = `h3.cell_to_children(parent, res)`; children whose centre is not on land are dropped (same rule as land fills); output columns `h3, res, lat, lng, parent, uc_id` (`uc_id` = urban polygon of that kind containing the child's centroid, nullable, parquet only). Children of a set of parents tile the parents' union, so coarse cell + children never double-draw except for the fractal notch along the region boundary (accepted; noted in §9.1).

### D4. Aggregation on a cell subset

`h3util.aggregate_raster` / `aggregate_rasters` / `raster_mean` gain `cells=`: a `CellSet` (cells, polygon bounds, polygons) built once; each window rasterises only the cells whose bounds intersect it and skips reading windows that touch none. Complete resolutions pass their hex set too (uniform; ocean cells are no longer computed and dropped). `raster_mean` caps `decimate` per resolution so a hex still spans about four block pixels across (`effective_decimate`): res 5 keeps 10, res 6 gets 7, res 7 gets 2.

### D5. Reference-distribution scoring (new SPEC §13.32)

For a derived resolution r, `plan.reference_res(r)` is the finest complete resolution below r (5 for both 6 and 7). `hazards` percentiles each hazard's raw value against the inhabited-and-ok values of the reference (`percentile_score(values, domain, reference=...)`); `score` does the same per dimension domain, takes wellbeing min-max bounds per source from the reference (`minmax_score(..., reference=...)`) and bivariate tercile cuts from the reference (`bivariate_class(..., cuts=...)`). Reference data comes from `sanity.load_merged(settings, ref)` restricted to inhabited hexes; missing reference files raise a plain-English "run <stage> for res 5 first". A derived score therefore reads "better than X% of inhabited res-5 hexes in the same domain".

### D6. Joiner direction (new SPEC §13.33)

`JoinSpec.higher_is` (optional) declares a joiner whose raw value runs opposite to its dimension (IMD employment deprivation feeding `jobs`). `score` reflects that joiner's percentile (`100 - p`) so every `{id}_score` obeys the dimension's `higher_is` and the client keeps applying one direction per dimension (§13.25 unchanged for the client). Raw values ship as published, with the joiner's unit text saying which way they run.

### D7. Export, manifest, tiles, publish

- `export` adds `ref` (nullable boolean, True only) to `out/hexes_r{res}.parquet` when the next finer plan entry's parquet exists (`h3 ∈ child.parent`), and writes `manifest["resolution_plan"]` (plan entries + `cells` per res).
- `tiles` reads zoom ranges, archives and slim zooms from `manifest["resolution_plan"]`, builds one archive per `archive` name (`hexes.pmtiles`, `hexes_fine.pmtiles`), each with its own cache and worker pool (the pool only loads that archive's layers), and records per layer `res`, `complete`, `overzoom` (true when no finer *present* layer is complete). `--archive` builds one archive; `--maxzoom` and `LAYER_ZOOMS` go away.
- `publish` ships `manifest.json` plus every `tiles[*].key`.
- Size: two archives keep each under the ~300 MB §14.10 guard (hexes 146 MB today; hexes_fine estimated 120-180 MB for ~400k res-6 + ~350k res-7 cells).

### D8. Web

- `lib/layers.ts`: `tileLayersFrom(manifest.tiles)` → `TileLayer { name, source, minzoom, maxzoom, res, complete, overzoom }` sorted by res; defaults when the manifest predates this session.
- `style.ts`: one MapLibre source per archive; a layer with `overzoom` gets no maxzoom; a coarse layer that has a finer layer above it fades its refined parents out from that layer's minzoom: `["step", ["zoom"], base, finerMin, ["case", ["==", ["get", "ref"], true], 0, base]]` on every paint opacity of its six style layers.
- `MapView`: adds every archive as a source; feature-state uses `feature.source`; `MAP_MAX_ZOOM` 14.
- Inspector: resolution label from the `res` attribute (`H3 res 7 hex (~5.2 km²)`); tag `grid` labelled "1 km grid"; domains `eu` ("EU") and `uk` ("England") on chips.

### D9. Sources and dimensions (SPEC §15, §20.6)

- `eurostat_census_grid_2021` (GISCO `Eurostat_Census-GRID_2021_V3.zip`, CSV, ETRS89-LAEA 1 km, 13 variables: T, M, F, Y_LT15, Y_1564, Y_GE65, EMP, NAT, EU_OTH, OTH, SAME, CHG_IN, CHG_OUT) → prep loader parses `GRD_ID` (`CRS3035RES1000mN{y}E{x}`) to cell-centre lat/lng, outputs `pop, pop_1564, emp, emp_rate, share_ge65`; `jobs` gains `{joiner: point_mean, res: grid, field: emp_rate, weight_field: pop_1564, domain: eu, label: eugrid}` after the ACS joiner.
- `eng_imd_2025` (MHCLG File 7 CSV, OGL v3, 33,755 LSOA 2021) + `ons_lsoa_2021` (ONS Open Geography LSOA Dec 2021 EW BGC, OGL v3) → prep loader joins on `LSOA21CD`, outputs `emp_dep_rate, health_dep, housing_barriers, income_dep_rate, imd_score, population, pop_working`; `jobs` (emp_dep_rate, `higher_is: worse`), `health` (health_dep, `higher_is: worse`), `house` (housing_barriers, same direction) gain `area_weighted_overlay` joiners at `res: tract`, domain `uk`, label `imd`, inserted before the OECD fallbacks.
- New resolution tag `grid` (statistical grid cell aggregated per hex), allowed for `raster_mean` and `point_mean`. LSOAs use `tract` (small statistical area).
- Both sources are verified first-hand before any loader is written (Task 1) and recorded in §15.

### D10. SPEC edits in the same PR

§4 invariant 4.2 tag list (+ `grid`); §5 diagram (`urban` line, `grid` line "resolution plan", `tiles` line two archives) mirrored in README; §6.1 (`res` 4-7, `ref`, `parent`/`uc_id` parquet-only, `grid` tag); §9.1 zoom plan table; §11 sizing (res-6/7 counts, timings, archive sizes, cap 300 MB per archive); §13.31-34 (SMOD mask; resolution plan + reference scoring; two archives + `ref` hiding; joiner `higher_is`); §15 rows (SMOD, Eurostat grid, IMD 2025, ONS LSOA); §16 Session 8 row → built; §20.3 note on `grid`; §20.6 rows. Not touched: §3, §16 Sessions 10/11 text.

## Global Constraints

- Missing data is never 0: derived-resolution scores, `ref`, `uc_id`, joiner outputs stay NA / absent (SPEC invariant 3).
- No socioeconomic layer below block group / output area at any resolution (SPEC §3, §16).
- Every real source `verified: confirmed` first-hand (URL, size, format, licence, key field) before code depends on it (SPEC §15, invariant 4); `fetch` refuses `VERIFY`.
- Tile attribute names short, §6.1 naming; `ref` is the only new tile attribute.
- `uv run pytest`, `uv run ruff check .`, `uv run python -m pipeline --fixtures all`, `cd web && npm test && npm run lint && npm run build` green at every commit; fixture world VERSION bumped to 7.
- Commit after each working step; branch `claude/neighborhood`; one PR against `main`; no attribution lines in commits.
- Laptop rules: `uv` from `~/.local/bin`, `PYTHONUTF8=1`, heavy runs in the background with `PYTHONUNBUFFERED=1` and a log file, Bash commands under ~8k chars, check pytest's exit status not the pipe's.

## Review Focus

1. `python -m pipeline --res 7 grid` when `hexes_r6.parquet` does not exist: a plain "run grid for res 6 first" error, never a KeyError (Task 6 test).
2. A child cell whose centre falls in the ocean: dropped, so its hidden parent leaves basemap sea, never a coloured sliver over water (Task 6 test).
3. A derived resolution whose reference domain has no inhabited hex (bbox run, or a domain absent at res 5): `_score` stays NA, never 0 or a crash (Task 7 test).
4. An urban cluster split across two raster windows: one polygon with one `uc_id`, not two (Task 4 test with a small window).
5. A manifest from before this session (no `resolution_plan`, no `complete`/`overzoom`): `tiles` says "run export first"; the web app falls back to hex4/hex5 defaults (Task 8 and Task 10 tests).

---

## File structure

Create:
- `pipeline/resplan.py` — plan loading, validation, `ResEntry`, `ResolutionPlan`.
- `pipeline/resolution_plan.yaml`, `pipeline/fixtures/resolution_plan.yaml`.
- `pipeline/stages/urban.py` — SMOD → urban polygons.
- `pipeline/reference.py` — reference frame for derived-resolution scoring.
- `pipeline/prep/eurostat_grid.py`, `pipeline/prep/imd.py`.
- `tests/test_resplan.py`, `tests/test_urban.py`, `tests/test_grid_plan.py`, `tests/test_reference.py`.
- `web/src/lib/layers.ts`, `web/src/lib/layers.test.ts`.
- `docs/superpowers/specs/2026-09-22-neighbourhood-resolution-design.md`, `docs/superpowers/plans/2026-09-22-session-8-neighbourhood-resolution.md`.

Modify: `pipeline/config.py`, `pipeline/__main__.py`, `pipeline/stages/__init__.py`, `pipeline/stages/{grid,pop,hazards,score,export,tiles,publish,dims}.py`, `pipeline/h3util.py`, `pipeline/joiners/raster_mean.py`, `pipeline/scoring.py`, `pipeline/manifest.py`, `pipeline/attrs.py`, `pipeline/registry.py`, `pipeline/prep/__init__.py`, `pipeline/sources.yaml`, `pipeline/dimensions.yaml`, `pipeline/fixtures/{make_fixtures.py,sources.yaml}`, `web/src/lib/{manifest.ts,style.ts,inspect.ts,dims.ts,config.ts,format.ts}`, `web/src/components/{MapView.tsx,MapApp.tsx,Inspector.tsx}`, `web/src/app/methodology/page.tsx`, `SPEC.md`, `README.md`, `CLAUDE.md`, `data/raw/CHECKSUMS`.

---

### Task 0: Branch, plan and spec documents

**Files:** create the two docs listed above.

- [ ] **Step 1: Branch**

```bash
git checkout main && git pull && git checkout -b claude/neighborhood
```

- [ ] **Step 2: Save the design and the plan into the repo**

Write `docs/superpowers/specs/2026-09-22-neighbourhood-resolution-design.md` with the Context, Design D1-D10 and Global Constraints sections of this file verbatim. Write `docs/superpowers/plans/2026-09-22-session-8-neighbourhood-resolution.md` with this whole file.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers && git commit -m "docs: Session 8 neighbourhood-resolution design and implementation plan"
```

---

### Task 1: Verify the four real sources first-hand and register them

**Files:**
- Modify: `pipeline/sources.yaml` (four entries), `pipeline/registry.py:288` (`REFERENCE_SOURCE_IDS`), `SPEC.md` §15, `data/raw/CHECKSUMS` (via `fetch`).

**Interfaces:** Produces source ids `ghsl_smod`, `eurostat_census_grid_2021`, `eng_imd_2025`, `ons_lsoa_2021` and the exact column names Task 9's loaders use (record them in §15 and in the source `processing:` text).

- [ ] **Step 1: Probe each URL (size, content type) and record what you see**

```bash
curl -sIL https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_SMOD_GLOBE_R2023A/GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss/V2-0/GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss_V2_0.zip | grep -iE "HTTP|content-length"
curl -sIL https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip | grep -iE "HTTP|content-length"
```

For IMD 2025 open https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025 and copy File 7's `assets.publishing.service.gov.uk/media/.../File_7_...csv` link; for the LSOA boundaries open the ONS Open Geography item "Lower layer Super Output Areas (December 2021) Boundaries EW BGC (V5)" and copy the GeoJSON download link from "I want to... > View API Resources" (`.../api/download/v1/items/<item>/geojson?layers=0`). If the hub answers a download with a 202 "generating" response, register the source as `access: manual` with a recipe (the HUD pattern, §13.30) instead of `direct`.

Also read the licence statements: JRC GHSL data page footer (CC BY 4.0), the GISCO population-grids page and its INSPIRE record for the census grid reuse terms, the gov.uk page footer (OGL v3), the ONS item page (OGL v3). Copy the exact wording into the `license` / `license_note` fields.

- [ ] **Step 2: Add the four entries to `pipeline/sources.yaml`** (mirror the `ghsl_pop` entry at lines 74-89; fill sizes and member names from Step 1 and Step 3)

```yaml
- id: ghsl_smod
  name: GHSL GHS-SMOD R2023A degree of urbanisation, epoch 2025, 30 arc-second
  group: reference
  access: direct
  url: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_SMOD_GLOBE_R2023A/GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss/V2-0/GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss_V2_0.zip
  format: geotiff-zip
  member: GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss_V2_0.tif
  crs: EPSG:4326
  native_res_m: ~1000
  nodata: -200
  license: CC BY 4.0
  verified: confirmed
  vintage: "2025 (R2023A V2.0, 2025-01-27)"
  attribution: "European Commission, Joint Research Centre (JRC), GHS-SMOD R2023A"
  processing: "classes 30 (urban centre) and >= 21 (urban cluster) polygonised by the urban stage (SPEC §13.31)"
  files: [GHS_SMOD_E2025_GLOBE_R2023A_4326_30ss_V2_0.zip]
- id: eurostat_census_grid_2021
  name: Eurostat Census 2021 population grid, 1 km (GISCO, V3)
  group: life
  access: direct
  url: https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip
  format: csv-zip
  member: <csv member name from Step 3>
  crs: EPSG:3035
  native_res_m: 1000
  license: <exact wording from Step 1>
  verified: confirmed
  vintage: "2021 census, V3 (2026-05-30)"
  attribution: "© Eurostat / GISCO, Census 2021 grid"
  processing: "GRD_ID -> cell centre in EPSG:3035 -> WGS84; emp_rate = EMP / Y_1564; confidential cells NaN (prep/eurostat_grid.py)"
  files: [Eurostat_Census-GRID_2021_V3.zip]
- id: eng_imd_2025
  name: English Indices of Deprivation 2025, File 7 (LSOA 2021 scores, ranks, deciles, denominators)
  group: life
  access: direct
  url: <File 7 CSV URL from Step 1>
  format: csv
  geometry: ons_lsoa_2021
  license: Open Government Licence v3.0
  verified: confirmed
  vintage: "IoD2025 (2025-10-30), LSOA 2021"
  attribution: "Ministry of Housing, Communities and Local Government, English Indices of Deprivation 2025"
  processing: "joined to ONS LSOA 2021 boundaries on LSOA21CD (prep/imd.py); England only"
  files: [<File 7 filename>]
- id: ons_lsoa_2021
  name: ONS Lower layer Super Output Areas (December 2021) Boundaries EW BGC
  group: reference
  access: direct   # or manual with a recipe if the hub download is not a stable URL
  url: <download URL from Step 1>
  format: geojson
  crs: EPSG:4326
  license: Open Government Licence v3.0 (contains OS data © Crown copyright and database right 2021)
  verified: confirmed
  vintage: "December 2021, BGC V5"
  attribution: "Office for National Statistics licensed under the Open Government Licence v3.0"
  files: [lsoa_2021_ew_bgc.geojson]
```

- [ ] **Step 3: Fetch and inspect**

```bash
export PATH="$HOME/.local/bin:$PATH"; PYTHONUTF8=1 uv run python -m pipeline fetch --only ghsl_smod --only eurostat_census_grid_2021 --only eng_imd_2025 --only ons_lsoa_2021
```

Then a scratch script (`scratchpad/inspect_sources.py`, not committed) prints: zip members and sizes (`zipfile`), the SMOD GeoTIFF shape/dtype/nodata/unique classes over a 2000x2000 window with `rasterio`, the Eurostat CSV header and 3 rows (look for `GRD_ID`, `T`, `Y_1564`, `EMP` and any confidentiality columns such as `*_CI` or `CONFIDENTIALSTATUS`), the IMD header (find the exact names of "LSOA code (2021)", "Employment Score (rate)", "Health Deprivation and Disability Score", "Barriers to Housing and Services Score", "Income Score (rate)", "Index of Multiple Deprivation (IMD) Score", "Total population: mid 2022 (excluding prisoners)", "Working age population 18-59/64: for use with Employment Deprivation Domain (excluding prisoners)") and the LSOA GeoJSON property names (`LSOA21CD`, `LSOA21NM`) and feature count (35,672 EW). Fix `member:`/`files:` in the yaml to match.

- [ ] **Step 4: Add `ghsl_smod` to the reference set**

In `pipeline/registry.py:288`: `REFERENCE_SOURCE_IDS = ("natural_earth_land", "geoboundaries_adm0", "geoboundaries_adm1", "ghsl_pop", "ghsl_smod")`.

- [ ] **Step 5: Log in SPEC §15** four `| 2026-09-22 | ... | **confirmed** ... | url |` rows with byte sizes, dimensions (SMOD 21600 x 43200 int16, nodata -200), row counts, column names and licence wording.

- [ ] **Step 6: Tests and commit**

```bash
uv run pytest tests/test_registry.py tests/test_fetch.py -q; uv run ruff check .
git add pipeline/sources.yaml pipeline/registry.py SPEC.md data/raw/CHECKSUMS && git commit -m "sources: GHS-SMOD, Eurostat census grid 2021, English IoD 2025 and ONS LSOA 2021 verified first-hand (SPEC §15)"
```

---

### Task 2: Resolution plan module and settings

**Files:**
- Create: `pipeline/resplan.py`, `pipeline/resolution_plan.yaml`, `pipeline/fixtures/resolution_plan.yaml`, `tests/test_resplan.py`
- Modify: `pipeline/config.py:13,36-48`, `pipeline/__main__.py:27-34`

**Interfaces:**
- Produces `resplan.load_plan(path) -> ResolutionPlan`; `ResEntry(res, fill, zooms, archive, parent, where, slim_below_zoom)` with `.complete`; `ResolutionPlan.resolutions() -> list[int]`, `.entry(res) -> ResEntry`, `.reference_res(res) -> int | None`, `.next_finer(res) -> ResEntry | None`, `.archives() -> dict[str, list[int]]`, `.to_manifest() -> list[dict]`; `Settings.plan` (cached), `Settings.plan_path`, `Settings.urban_path`; `settings.res` defaults to `plan.resolutions()`.

- [ ] **Step 1: Failing tests** (`tests/test_resplan.py`)

```python
from pathlib import Path
import pytest
import yaml
from pipeline import resplan
from pipeline.config import Settings

def _write(tmp_path: Path, entries) -> Path:
    p = tmp_path / "plan.yaml"
    p.write_text(yaml.safe_dump({"resolutions": entries}), encoding="utf-8")
    return p

GOOD = [
    {"res": 4, "fill": "land", "zooms": [2, 4], "archive": "hexes", "slim_below_zoom": 3},
    {"res": 5, "fill": "land", "zooms": [5, 7], "archive": "hexes"},
    {"res": 6, "fill": "children", "parent": 5, "where": {"countries": ["XA"], "urban": "cluster"}, "zooms": [8, 9], "archive": "hexes_fine"},
    {"res": 7, "fill": "children", "parent": 6, "where": {"urban": "centre"}, "zooms": [10, 13], "archive": "hexes_fine"},
]

def test_plan_loads_and_answers_questions(tmp_path):
    plan = resplan.load_plan(_write(tmp_path, GOOD))
    assert plan.resolutions() == [4, 5, 6, 7]
    assert plan.entry(6).parent == 5 and plan.entry(6).where["countries"] == ["XA"]
    assert plan.reference_res(7) == 5 and plan.reference_res(6) == 5 and plan.reference_res(5) is None
    assert plan.next_finer(5).res == 6 and plan.next_finer(7) is None
    assert plan.archives() == {"hexes": [4, 5], "hexes_fine": [6, 7]}
    assert plan.to_manifest()[2]["where"] == {"countries": ["XA"], "urban": "cluster"}
    assert plan.entry(4).complete and not plan.entry(6).complete

@pytest.mark.parametrize("bad, message", [
    ([{"res": 5, "fill": "land", "zooms": [2, 4]}, {"res": 4, "fill": "land", "zooms": [5, 7]}], "ascending"),
    ([{"res": 4, "fill": "children", "parent": 3, "zooms": [2, 4]}], "first entry"),
    ([{"res": 4, "fill": "land", "zooms": [2, 4]}, {"res": 6, "fill": "children", "parent": 5, "zooms": [5, 7]}], "parent"),
    ([{"res": 4, "fill": "land", "zooms": [2, 5]}, {"res": 5, "fill": "land", "zooms": [5, 7]}], "overlap"),
    ([{"res": 4, "fill": "land", "zooms": [2, 4]}, {"res": 5, "fill": "children", "parent": 4, "where": {"urban": "town"}, "zooms": [5, 7]}], "urban"),
    ([{"res": 11, "fill": "land", "zooms": [2, 4]}], "between 4 and 10"),
])
def test_plan_validation_speaks_plain_english(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        resplan.load_plan(_write(tmp_path, bad))

def test_real_and_fixture_plans_are_valid():
    root = Path(__file__).resolve().parents[1]
    assert resplan.load_plan(root / "pipeline" / "resolution_plan.yaml").resolutions() == [4, 5, 6, 7]
    assert resplan.load_plan(root / "pipeline" / "fixtures" / "resolution_plan.yaml").entry(6).where["countries"] == ["XA"]

def test_settings_default_res_comes_from_the_plan(settings):
    assert settings.res == [4]  # conftest passes res=[4]
    fresh = Settings(root=settings.root, fixtures=True)
    assert fresh.res == fresh.plan.resolutions() == [4, 5, 6, 7]
    assert fresh.urban_path.name == "urban.parquet"
```

- [ ] **Step 2: Run, expect ImportError** — `uv run pytest tests/test_resplan.py -q`

- [ ] **Step 3: Implement `pipeline/resplan.py`**

```python
"""Resolution plan (SPEC §9.1, §13.32): which H3 resolutions are built, where, and at which zooms.

`land` entries cover every land cell; `children` entries are the H3 children of the parent cells
that match any `where` rule (countries: ISO2 list of the parent centroid's country; urban:
centre | cluster, a parent whose polygon touches an urban polygon of that kind from the urban
stage). Any res 4-10 is allowed so Session 11 adds res 9/10 by editing the yaml only.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import yaml

FILLS = ("land", "children")
URBAN_KINDS = ("centre", "cluster")
RULE_KEYS = ("countries", "urban")
RES_MIN, RES_MAX = 4, 10
_ARCHIVE = re.compile(r"^[a-z][a-z0-9_]*$")

@dataclass(frozen=True)
class ResEntry:
    res: int
    fill: str
    zooms: tuple[int, int]
    archive: str = "hexes"
    parent: int | None = None
    where: dict = field(default_factory=dict)
    slim_below_zoom: int | None = None

    @property
    def complete(self) -> bool:
        return self.fill == "land"

    def to_manifest(self) -> dict:
        return {"res": self.res, "fill": self.fill, "parent": self.parent, "where": dict(self.where), "zooms": list(self.zooms), "archive": self.archive, "slim_below_zoom": self.slim_below_zoom, "complete": self.complete}

@dataclass(frozen=True)
class ResolutionPlan:
    entries: tuple[ResEntry, ...]

    def resolutions(self) -> list[int]:
        return [e.res for e in self.entries]

    def entry(self, res: int) -> ResEntry:
        for e in self.entries:
            if e.res == res:
                return e
        raise KeyError(f"res {res} is not in the resolution plan (plan has {self.resolutions()})")

    def reference_res(self, res: int) -> int | None:
        """Finest complete resolution coarser than `res`; None for a complete resolution."""
        if self.entry(res).complete:
            return None
        below = [e.res for e in self.entries if e.complete and e.res < res]
        return max(below) if below else None

    def next_finer(self, res: int) -> ResEntry | None:
        finer = [e for e in self.entries if e.res > res]
        return finer[0] if finer else None

    def archives(self) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for e in self.entries:
            out.setdefault(e.archive, []).append(e.res)
        return out

    def to_manifest(self) -> list[dict]:
        return [e.to_manifest() for e in self.entries]

def _entry(raw: dict, previous: list[ResEntry]) -> ResEntry:
    res = int(raw.get("res", -1))
    if not RES_MIN <= res <= RES_MAX:
        raise ValueError(f"resolution plan: res must be between {RES_MIN} and {RES_MAX}, got {res}")
    if previous and res <= previous[-1].res:
        raise ValueError(f"resolution plan: entries must be ascending (res {res} after {previous[-1].res})")
    fill = raw.get("fill")
    if fill not in FILLS:
        raise ValueError(f"resolution plan res {res}: fill must be one of {FILLS}")
    if not previous and fill != "land":
        raise ValueError("resolution plan: the first entry must be a complete `land` fill")
    zooms = tuple(int(z) for z in (raw.get("zooms") or ()))
    if len(zooms) != 2 or zooms[0] > zooms[1]:
        raise ValueError(f"resolution plan res {res}: zooms must be [min, max]")
    if previous and zooms[0] <= previous[-1].zooms[1]:
        raise ValueError(f"resolution plan res {res}: zooms {zooms} overlap res {previous[-1].res} {previous[-1].zooms}")
    archive = str(raw.get("archive", "hexes"))
    if not _ARCHIVE.match(archive):
        raise ValueError(f"resolution plan res {res}: archive name {archive!r} must be lowercase letters, digits, underscores")
    parent = raw.get("parent")
    where = dict(raw.get("where") or {})
    if fill == "children":
        if parent is None or int(parent) not in [p.res for p in previous]:
            raise ValueError(f"resolution plan res {res}: parent must name an earlier entry, got {parent}")
        parent = int(parent)
        if not where:
            raise ValueError(f"resolution plan res {res}: children entries need a `where` rule")
    unknown = set(where) - set(RULE_KEYS)
    if unknown:
        raise ValueError(f"resolution plan res {res}: unknown where keys {sorted(unknown)} (allowed {RULE_KEYS})")
    if "urban" in where and where["urban"] not in URBAN_KINDS:
        raise ValueError(f"resolution plan res {res}: urban must be one of {URBAN_KINDS}")
    if "countries" in where:
        where["countries"] = [str(c).upper() for c in where["countries"]]
    slim = raw.get("slim_below_zoom")
    return ResEntry(res=res, fill=fill, zooms=zooms, archive=archive, parent=parent, where=where, slim_below_zoom=None if slim is None else int(slim))

def load_plan(path: Path) -> ResolutionPlan:
    if not path.exists():
        raise FileNotFoundError(f"resolution plan {path} is missing")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: list[ResEntry] = []
    for item in raw.get("resolutions") or []:
        entries.append(_entry(item, entries))
    if not entries:
        raise ValueError(f"resolution plan {path} has no `resolutions` entries")
    return ResolutionPlan(tuple(entries))
```

Write the two yaml files from D1 (fixture one with `countries: [XA]`).

- [ ] **Step 4: Settings** (`pipeline/config.py`)

Replace `H3_RES` with a comment pointing at the plan; `res: list[int] = field(default_factory=list)`; add:

```python
    def __post_init__(self) -> None:
        if not self.res:
            self.res = self.plan.resolutions()

    @property
    def plan_path(self) -> Path:
        if self.fixtures:
            return self.root / "pipeline" / "fixtures" / "resolution_plan.yaml"
        return self.root / "pipeline" / "resolution_plan.yaml"

    @property
    def plan(self):
        """The resolution plan, loaded once (a plain attribute, not a dataclass field, so
        `Settings(...)` keeps its signature and `describe()` / `asdict` ignore it)."""
        from . import resplan  # local import: config stays import-light
        if getattr(self, "_plan", None) is None:
            self._plan = resplan.load_plan(self.plan_path)
        return self._plan

    @property
    def urban_path(self) -> Path:
        return self.interim_dir / "urban.parquet"
```

Keep `__main__.py` behaviour (`--res` subset) and validate: `unknown = set(res) - set(settings.plan.resolutions())` → `typer.BadParameter(f"--res {sorted(unknown)} is not in {settings.plan_path.name}")`. Update the `--res` help text: "H3 resolution(s) from the plan; default all".

- [ ] **Step 5: Run tests, ruff; commit** — `git commit -m "resplan: resolution plan file, validation and Settings.plan (SPEC §9.1)"`

---

### Task 3: Fixture world v7

**Files:**
- Modify: `pipeline/fixtures/make_fixtures.py` (VERSION 7, new generators, `build()` calls, a spot check), `pipeline/fixtures/sources.yaml` (4 entries), `tests/test_stages.py::test_fixture_generation_is_deterministic` (already covers determinism).

**Interfaces:** fixture files `smod.tif` (int16-like float32, nodata -200), `eurostat_grid.csv` (`lat, lng, pop, pop_1564, emp, emp_rate, share_ge65`), `lsoa.gpkg` (`LSOA21CD, LSOA21NM, emp_dep_rate, health_dep, housing_barriers, income_dep_rate, imd_score, population, pop_working`, polygons), fixture source ids `ghsl_smod`, `eurostat_census_grid_2021`, `eng_imd_2025`, `ons_lsoa_2021`.

- [ ] **Step 1: Failing test** (append to `tests/test_stages.py`)

```python
def test_fixture_world_has_urban_classes_and_grids(fixture_dir):
    import rasterio
    with rasterio.open(fixture_dir / "smod.tif") as src:
        arr = src.read(1)
        assert src.nodata == -200 and {10, 11, 21, 30} <= set(np.unique(arr[arr != -200]).astype(int))
        row, col = src.index(11.0, 43.0)   # Alder centre
        assert arr[row, col] == 30
        row, col = src.index(12.5, 40.7)   # desert
        assert arr[row, col] == 11
    grid = pd.read_csv(fixture_dir / "eurostat_grid.csv")
    assert {"lat", "lng", "pop", "pop_1564", "emp", "emp_rate", "share_ge65"} <= set(grid.columns)
    assert grid["lng"].between(10, 12).all()          # XKA only
    lsoa = gpd.read_file(fixture_dir / "lsoa.gpkg")
    assert {"LSOA21CD", "emp_dep_rate", "health_dep", "housing_barriers", "population", "pop_working"} <= set(lsoa.columns)
    assert lsoa.total_bounds[0] >= 12.0                 # XKB B-Mid only
```

(`np`, `gpd` imports at the top of the test file; `fixture_dir` is the session fixture from `tests/conftest.py`.)

- [ ] **Step 2: Generators** (`make_fixtures.py`)

```python
NODATA_SMOD = -200.0
SMOD_CENTRE_PX, SMOD_CLUSTER_PX = 1000.0, 200.0  # persons per pixel thresholds -> class 30 / 21

def smod_raster(pop: np.ndarray, land: np.ndarray) -> np.ndarray:
    """Degree-of-urbanisation classes from the fixture population: 30 where dense (Alder, Birch,
    Cedar centres), 21 around them (Dune too), 11 elsewhere on land, 10 water, nodata where the
    population raster is nodata."""
    smod = np.full(pop.shape, 10.0)
    smod[land] = 11.0
    smod[land & (pop >= SMOD_CLUSTER_PX)] = 21.0
    smod[land & (pop >= SMOD_CENTRE_PX)] = 30.0
    smod[pop == NODATA_POP] = NODATA_SMOD
    return smod

def eurostat_grid(LNG, LAT, pop, land) -> pd.DataFrame:
    """A 1 km-ish statistical grid over XKA (lng < 12): one point per pixel with counts."""
    sel = land & (LNG < 12.0) & (pop > 0)
    lng, lat, p = LNG[sel], LAT[sel], pop[sel]
    emp_rate = np.clip(0.5 + 0.2 * (lng - 10.0) / 2.0 + 0.1 * (lat - 42.0) / 2.0, 0.3, 0.9)  # rises east and north
    pop_1564 = np.round(p * 0.65)
    return pd.DataFrame({"lat": lat, "lng": lng, "pop": np.round(p), "pop_1564": pop_1564, "emp": np.round(pop_1564 * emp_rate), "emp_rate": emp_rate, "share_ge65": 0.2})

def lsoa_layer(land_geom) -> gpd.GeoDataFrame:
    """0.05 degree squares over B-Mid (XKB, 12-14 x 41.5-43) standing in for LSOAs with IMD scores;
    deprivation rises northwards so jobs/health/house scores have a gradient."""
    rows = []
    x0s = np.arange(12.0, 14.0, 0.05); y0s = np.arange(41.5, 43.0, 0.05)
    for i, x0 in enumerate(x0s):
        for j, y0 in enumerate(y0s):
            geom = box(x0, y0, x0 + 0.05, y0 + 0.05).intersection(land_geom)
            if geom.is_empty:
                continue
            t = (y0 - 41.5) / 1.5
            rows.append({"LSOA21CD": f"X0{i:02d}{j:02d}", "LSOA21NM": f"B-Mid {i}{j}", "emp_dep_rate": 0.05 + 0.2 * t, "health_dep": -1.0 + 2.0 * t, "housing_barriers": 10.0 + 30.0 * t, "income_dep_rate": 0.08 + 0.25 * t, "imd_score": 10.0 + 40.0 * t, "population": 1500.0, "pop_working": 900.0, "geometry": geom})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=4326)
```

In `build()` after `pop.tif`: `_write_tif(out / "smod.tif", smod_raster(pop_arr, land), transform, NODATA_SMOD)` (keep the population array in a variable instead of recomputing), `eurostat_grid(LNG, LAT, pop_arr, land).to_csv(out / "eurostat_grid.csv", index=False)`, `lsoa_layer(land_gdf.geometry.iloc[0]).to_file(out / "lsoa.gpkg", driver="GPKG")`. Bump `VERSION = 7`. Add `Spot("Alder centre res 7", 43.0, 11.0, "res-7 hex inside the Alder urban centre")` to `SPOT_CHECKS` (sanity prints per res; harmless at res 4).

- [ ] **Step 3: Fixture sources** (`pipeline/fixtures/sources.yaml`, same shape as the `ghsl_pop` entry)

`ghsl_smod` (geotiff `smod.tif`, `nodata: -200`, group reference), `eurostat_census_grid_2021` (csv `eurostat_grid.csv`, group life), `eng_imd_2025` (geopackage `lsoa.gpkg`, group life, no `geometry:` key: the fixture is already joined), `ons_lsoa_2021` (geopackage `lsoa.gpkg`, group reference). All `access: fixture`, `verified: confirmed`, `license: CC0 (synthetic fixture)`.

- [ ] **Step 4: Regenerate, test, commit**

```bash
PYTHONUTF8=1 uv run python -m pipeline.fixtures.make_fixtures && uv run pytest -q
git commit -am "fixtures v7: SMOD classes, a 1 km statistical grid and LSOA-like deprivation polygons"
```

---

### Task 4: `urban` stage

**Files:**
- Create: `pipeline/stages/urban.py`, `tests/test_urban.py`
- Modify: `pipeline/stages/__init__.py` (`STAGE_ORDER`), `pipeline/__main__.py` (command), `pipeline/h3util.py:136` (rename `_iter_windows` → `iter_windows`, keep the old name as an alias).

**Interfaces:** `urban.run(settings) -> dict[str, int]` (polygons per kind); `urban.polygons_from_raster(path, bbox=None, nodata=None, window_size=2048) -> gpd.GeoDataFrame[uc_id, kind, area_km2, geometry]`; `urban.KINDS = {"centre": 30, "cluster": 21}`; output `settings.urban_path`.

- [ ] **Step 1: Failing tests** (`tests/test_urban.py`)

```python
import geopandas as gpd
from shapely.geometry import Point
from pipeline.stages import fetch, urban

def test_urban_polygons_cover_the_towns(settings):
    fetch.run(settings)
    counts = urban.run(settings)
    gdf = gpd.read_parquet(settings.urban_path)
    centres = gdf[gdf["kind"] == "centre"]
    assert counts["centre"] == len(centres) == 3                      # Alder, Birch, Cedar
    assert centres["uc_id"].tolist() == [1, 2, 3] and centres["area_km2"].is_monotonic_decreasing
    assert centres.contains(Point(11.0, 43.0)).any() and not centres.contains(Point(12.5, 40.7)).any()
    clusters = gdf[gdf["kind"] == "cluster"]
    assert len(clusters) == 4 and clusters.contains(Point(13.6, 43.6)).any()   # Dune is a cluster only

def test_pieces_split_across_windows_are_one_polygon(settings):
    fetch.run(settings)
    path = settings.raw("ghsl_smod") / "smod.tif"
    small = urban.polygons_from_raster(path, window_size=64)       # Cedar (radius ~9 px) crosses window edges
    big = urban.polygons_from_raster(path, window_size=2048)
    assert len(small) == len(big) and abs(small["area_km2"].sum() - big["area_km2"].sum()) < 1e-6

def test_urban_is_cached(settings, capsys):
    fetch.run(settings); urban.run(settings); capsys.readouterr()
    urban.run(settings)
    assert "up to date" in capsys.readouterr().out
```

- [ ] **Step 2: Run, expect failure** — `uv run pytest tests/test_urban.py -q`

- [ ] **Step 3: Implement**

```python
"""``urban`` stage (SPEC §5, §13.31): GHS-SMOD degree-of-urbanisation classes -> urban polygons.

Writes ``data/interim/urban.parquet`` (GeoParquet) with one row per polygon: ``uc_id`` (ordinal
by area within its kind, 1 = largest), ``kind`` (``centre`` = class 30, ``cluster`` = class >= 21,
which includes the centres), ``area_km2`` (EPSG:6933) and the WGS84 geometry. The grid stage
refines parent cells that touch these polygons (resolution plan `where: {urban: kind}`); Session
11 reuses the same layer for block hexes, which is why it is saved with ids rather than kept in
memory.
"""
from __future__ import annotations
import time
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio import features
from shapely.geometry import shape
from .. import h3util, rawfiles, stage_cache
from ..config import BBox, Settings
from ..registry import load_sources

SMOD_SOURCE = "ghsl_smod"
KINDS = {"centre": 30, "cluster": 21}  # kind -> minimum class

def polygons_from_raster(path: Path, bbox: BBox | None = None, nodata: float | None = None, window_size: int = 2048) -> gpd.GeoDataFrame:
    pieces: dict[str, list] = {k: [] for k in KINDS}
    with rasterio.open(path) as src:
        nd = nodata if nodata is not None else src.nodata
        for window in h3util.iter_windows(src, bbox, window_size):
            arr = src.read(1, window=window)
            valid = h3util._mask_valid(arr.astype("float64"), nd)
            transform = src.window_transform(window)
            for kind, lo in KINDS.items():
                mask = valid & (arr >= lo)
                if not mask.any():
                    continue
                for geom, _ in features.shapes(mask.astype("uint8"), mask=mask, transform=transform):
                    pieces[kind].append(shape(geom))
    frames = []
    for kind in KINDS:
        if not pieces[kind]:
            frames.append(gpd.GeoDataFrame({"uc_id": pd.Series(dtype="int64"), "kind": pd.Series(dtype=str), "area_km2": pd.Series(dtype="float64")}, geometry=[], crs=4326))
            continue
        merged = shapely.unary_union(pieces[kind])  # joins pieces that met at window edges
        polys = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
        gdf = gpd.GeoDataFrame({"kind": kind}, geometry=polys, crs=4326)
        gdf["area_km2"] = gdf.to_crs(6933).area / 1e6
        gdf = gdf.sort_values("area_km2", ascending=False, kind="stable").reset_index(drop=True)
        gdf.insert(0, "uc_id", np.arange(1, len(gdf) + 1))
        frames.append(gdf)
    return pd.concat(frames, ignore_index=True)[["uc_id", "kind", "area_km2", "geometry"]]

def run(settings: Settings) -> dict[str, int]:
    settings.ensure_dirs()
    src = load_sources(settings.sources_path)[SMOD_SOURCE]
    raster = rawfiles.resolve_raster(settings, src)   # extracts the zip member once
    out = settings.urban_path
    params = {"stage": "urban", "bbox": settings.bbox, "kinds": KINDS}
    if stage_cache.is_fresh(out, [raster], params, settings.force):
        gdf = gpd.read_parquet(out, columns=["kind"])
        counts = gdf["kind"].value_counts().to_dict()
        print(f"urban  up to date ({counts}), skipping")
        return {k: int(counts.get(k, 0)) for k in KINDS}
    t0 = time.time()
    nd = src.extra.get("nodata")
    gdf = polygons_from_raster(raster, settings.bbox, None if nd is None else float(nd))
    gdf.to_parquet(out, index=False)
    counts = {k: int((gdf["kind"] == k).sum()) for k in KINDS}
    stage_cache.record(out, [raster], params, {"counts": counts})
    print(f"urban  {counts['centre']} urban centres, {counts['cluster']} urban clusters in {time.time() - t0:.1f}s -> {out.name}")
    return counts
```

`STAGE_ORDER = ["fetch", "urban", "grid", ...]`; `@app.command() def urban(ctx)` docstring "GHS-SMOD urban centres and clusters as polygons (SPEC §13.31)". Check `rawfiles.resolve_raster` handles `geotiff-zip` + `member` (it does for `ghsl_pop`).

- [ ] **Step 4: Test, ruff, commit** — `git commit -m "urban stage: GHS-SMOD classes -> saved urban centre / cluster polygons with ids (SPEC §13.31)"`

---

### Task 5: Aggregate on a cell subset; resolution-aware decimation

**Files:**
- Modify: `pipeline/h3util.py:166-216,284-380`, `pipeline/joiners/raster_mean.py`, `pipeline/stages/pop.py:46`, `pipeline/stages/hazards.py` (`flood_fraction`), `pipeline/stages/dims.py:82-86`
- Test: `tests/test_h3util.py`, `tests/test_joiners.py`

**Interfaces:** `h3util.CellSet.from_cells(cells: Iterable[str]) -> CellSet` with `.cells: list[str]`, `.bounds: np.ndarray (N,4)`, `.polygons: list`, `.in_bounds(minx, miny, maxx, maxy) -> np.ndarray[int]`; `aggregate_raster(..., cells: CellSet | Iterable[str] | None = None)`, same on `aggregate_rasters`; `raster_mean(hexes, path, res, ..., cells=None)` (uses `hexes["h3"]` when None); `raster_mean.effective_decimate(decimate: int, res: int, pixel_deg: float) -> int`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_h3util.py
def test_aggregate_on_a_cell_subset_matches_the_full_fill(fixture_dir):
    path = fixture_dir / "pop.tif"
    full = h3util.aggregate_raster(path, 5, "sum").set_index("h3")["value"]
    some = full.index[:20].tolist()
    part = h3util.aggregate_raster(path, 5, "sum", cells=some).set_index("h3")["value"]
    assert set(part.index) == set(some)
    pd.testing.assert_series_equal(part.sort_index(), full.loc[some].sort_index(), check_names=False)

def test_cellset_bounds_pick_only_touching_cells():
    cs = h3util.CellSet.from_cells([h3.latlng_to_cell(43.0, 11.0, 7), h3.latlng_to_cell(40.7, 12.5, 7)])
    assert cs.in_bounds(10.9, 42.9, 11.1, 43.1).tolist() == [0]
    assert cs.in_bounds(0, 0, 1, 1).size == 0

# tests/test_joiners.py
def test_effective_decimate_keeps_a_few_pixels_across_a_hex():
    from pipeline.joiners.raster_mean import effective_decimate
    assert effective_decimate(10, 5, 0.001) == 10
    assert effective_decimate(10, 6, 0.001) == 7
    assert effective_decimate(10, 7, 0.001) == 2
    assert effective_decimate(1, 7, 0.001) == 1
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement**

`h3util.py`:

```python
@dataclass
class CellSet:
    """The cells a raster aggregation is for: polygons and bounds built once, so every window
    rasterizes only the cells that touch it (a derived resolution has ~350k cells scattered over
    the world, not the 28 million a full res-7 fill of every window would produce)."""
    cells: list[str]
    bounds: np.ndarray
    polygons: list[Polygon]

    @classmethod
    def from_cells(cls, cells: Iterable[str]) -> "CellSet":
        cells = sorted(set(cells))
        polys = [cell_polygon(c) for c in cells]
        bounds = np.array([p.bounds for p in polys], dtype="float64").reshape(len(polys), 4)
        return cls(cells, bounds, polys)

    def in_bounds(self, minx: float, miny: float, maxx: float, maxy: float) -> np.ndarray:
        if not self.cells:
            return np.zeros(0, dtype="int64")
        b = self.bounds
        m = (b[:, 0] <= maxx) & (b[:, 2] >= minx) & (b[:, 1] <= maxy) & (b[:, 3] >= miny) & ((b[:, 2] - b[:, 0]) <= 180)
        return np.flatnonzero(m)
```

`_cells_index(bounds, transform, shape, res, cellset=None)`: when `cellset` is given, `idx_sel = cellset.in_bounds(*bounds)`; `cells = [cellset.cells[i] for i in idx_sel]`; `shapes = [(cellset.polygons[i], k) for k, i in enumerate(idx_sel, start=1)]`; rasterize as today. `_window_cells_index(..., cellset=None)` passes it through. In `aggregate_raster` / `aggregate_rasters`: `cellset = cells if isinstance(cells, CellSet) else (CellSet.from_cells(cells) if cells is not None else None)`; before `src.read`, `if cellset is not None and cellset.in_bounds(*rasterio.windows.bounds(window, src.transform)).size == 0: continue`. Rename `_iter_windows` → `iter_windows` (alias `_iter_windows = iter_windows`).

`raster_mean.py`: signature `raster_mean(hexes, path, res, *, band=1, nodata=None, decimate=1, sample="mean", bbox=None, cells=None)`; `cellset = CellSet.from_cells(cells if cells is not None else hexes["h3"])`; for `sample == "mean"`: `d = effective_decimate(decimate, res, pixel_deg)` where `pixel_deg = abs(src.transform.a)` read via `rasterio.open`; call `aggregate_raster(..., decimate=d, cells=cellset)`; add

```python
def effective_decimate(decimate: int, res: int, pixel_deg: float) -> int:
    """Cap the block-averaging factor so a hex still spans ~4 coarse pixels across: a res-7 hex
    (edge 1.2 km) over 100 m pixels averages 2x2 blocks, res 5 keeps the registry's 10."""
    if decimate <= 1:
        return 1
    edge_deg = h3.average_hexagon_edge_length(res, unit="km") / 111.0
    return int(max(1, min(decimate, edge_deg / (pixel_deg * 4))))
```

`pop.py`: `agg = h3util.aggregate_raster(raster, res, "sum", bbox=settings.bbox, cells=hexes["h3"])` (read the hexes parquet first; it already merges onto it). `hazards.flood_fraction(rasters, res, depth_min, bbox, cells)` passes `cells=hexes["h3"]`. `dims.run_joiner`: pass `cells=hexes["h3"]` to `raster_mean` (hexes is the full frame at this res).

- [ ] **Step 4: Full pytest (fixture results at res 4 must be unchanged: `tests/test_hazards.py`, `test_extras.py`), ruff, commit** — `git commit -m "h3util: aggregate rasters over an explicit cell set; raster_mean caps decimation per resolution"`

---

### Task 6: `grid` stage takes the resolution plan

**Files:**
- Modify: `pipeline/stages/grid.py` (whole file), `pipeline/stages/pop.py`, `pipeline/stages/admin.py`, `pipeline/stages/hazards.py`, `pipeline/stages/dims.py` (only: read hexes with `columns=["h3", "lat", "lng"]` is already the case; no change unless a stage reads all columns)
- Test: `tests/test_grid_plan.py`

**Interfaces:** `grid.run(settings) -> dict[int, int]`; `grid.refine(parents: pd.DataFrame, entry: ResEntry, land: gpd.GeoDataFrame, urban: gpd.GeoDataFrame | None, adm0: gpd.GeoDataFrame | None, iso_overrides: dict) -> pd.DataFrame[h3, res, lat, lng, parent, uc_id]`; derived hexes parquet carries `parent` (str) and `uc_id` (Int64, nullable).

- [ ] **Step 1: Failing tests** (`tests/test_grid_plan.py`)

```python
import h3
import pandas as pd
import pytest
from pipeline.stages import fetch, grid, urban

def _prepare(settings, res):
    settings.res = res
    fetch.run(settings); urban.run(settings); grid.run(settings)

def test_children_only_where_the_plan_says(settings):
    _prepare(settings, [4, 5, 6, 7])
    r5 = pd.read_parquet(settings.hexes_path(5)); r6 = pd.read_parquet(settings.hexes_path(6)); r7 = pd.read_parquet(settings.hexes_path(7))
    assert set(r6["parent"]) <= set(r5["h3"]) and set(r7["parent"]) <= set(r6["h3"])
    assert (r6["h3"].map(lambda c: h3.cell_to_parent(c, 5)) == r6["parent"]).all()
    alder7, desert7, cedar6 = h3.latlng_to_cell(43.0, 11.0, 7), h3.latlng_to_cell(40.7, 12.5, 7), h3.latlng_to_cell(42.5, 13.0, 6)
    assert alder7 in set(r7["h3"]) and desert7 not in set(r7["h3"])
    assert cedar6 in set(r6["h3"])                          # XB is not a plan country: Cedar is refined through its cluster
    assert h3.latlng_to_cell(40.7, 12.5, 6) not in set(r6["h3"])   # desert in XB: no rule matches
    assert h3.latlng_to_cell(41.0, 10.5, 6) in set(r6["h3"])       # rural XA: country rule
    assert r7.set_index("h3").loc[alder7, "uc_id"] == 1 or r7.set_index("h3").loc[alder7, "uc_id"] in (1, 2, 3)
    assert r7["uc_id"].notna().all()

def test_children_with_an_ocean_centre_are_dropped(settings):
    _prepare(settings, [4, 5, 6])
    r6 = pd.read_parquet(settings.hexes_path(6))
    assert h3.latlng_to_cell(40.3, 13.8, 6) not in set(r6["h3"])

def test_missing_parent_is_a_plain_error(settings):
    settings.res = [7]
    fetch.run(settings); urban.run(settings)
    with pytest.raises(FileNotFoundError, match="run grid for res 6 first"):
        grid.run(settings)

def test_downstream_stages_run_on_a_derived_resolution(settings):
    from pipeline.stages import admin, pop
    _prepare(settings, [4, 5, 6, 7])
    pop.run(settings); admin.run(settings)
    p7 = pd.read_parquet(settings.stage_path("pop", 7))
    assert p7["population"].sum() > 0 and p7["inhabited"].any()
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement `grid.py`**

```python
"""``grid`` stage (SPEC §5, §9.1, §13.32): the resolution plan -> one hexes parquet per resolution.

`land` entries: H3 cells whose centre is on Natural Earth land (as before). `children` entries:
the H3 children of every parent cell that matches a plan rule (country of the parent centroid,
or the parent polygon touching an urban polygon of the requested kind), keeping only children
whose centre is on land. Output columns ``h3, res, lat, lng`` plus ``parent`` and ``uc_id``
(nullable, the urban polygon under the child's centroid) for derived resolutions.
"""
from __future__ import annotations
import time
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box
from .. import h3util, stage_cache
from ..config import Settings
from ..joiners.polygon_centroid import polygon_centroid
from ..prep.util import iso3_to_iso2
from ..registry import load_sources
from ..resplan import ResEntry
from .admin import ADM0_SOURCE

LAND_SOURCE = "natural_earth_land"

def land_path(settings): ...  # unchanged
def build_hexes(land, res): ...  # unchanged

def _on_land(land: gpd.GeoDataFrame, lng: np.ndarray, lat: np.ndarray) -> np.ndarray:
    tree = shapely.STRtree(land.geometry.values)
    pts = shapely.points(lng, lat)
    hit = np.zeros(len(pts), dtype=bool)
    hit[tree.query(pts, predicate="within")[0]] = True
    return hit

def refine(parents: pd.DataFrame, entry: ResEntry, land: gpd.GeoDataFrame, urban: gpd.GeoDataFrame | None, adm0: gpd.GeoDataFrame | None, iso_overrides: dict[str, str]) -> pd.DataFrame:
    match = np.zeros(len(parents), dtype=bool)
    if countries := entry.where.get("countries"):
        iso2 = iso3_to_iso2(polygon_centroid(parents, adm0, field="shapeGroup"), iso_overrides)
        match |= iso2.isin(countries).to_numpy()
    kind = entry.where.get("urban")
    urban_kind = None
    if kind:
        urban_kind = urban[urban["kind"] == kind][["uc_id", "geometry"]]
        polys = gpd.GeoDataFrame({"i": np.arange(len(parents))}, geometry=h3util.cell_polygons(parents["h3"]), crs=4326)
        hit = gpd.sjoin(polys, urban_kind[["geometry"]], predicate="intersects", how="inner")
        match[hit["i"].unique()] = True
    kids, parent_of = [], []
    for p in parents.loc[match, "h3"]:
        c = h3.cell_to_children(p, entry.res)
        kids += c; parent_of += [p] * len(c)
    lat, lng = h3util.cell_centroids(kids)
    df = pd.DataFrame({"h3": kids, "res": entry.res, "lat": lat, "lng": lng, "parent": parent_of})
    df = df[_on_land(land, df["lng"].to_numpy(), df["lat"].to_numpy())].reset_index(drop=True)
    df["uc_id"] = pd.array([pd.NA] * len(df), dtype="Int64")
    if urban_kind is not None and len(df):
        pts = gpd.GeoDataFrame({"i": np.arange(len(df))}, geometry=gpd.points_from_xy(df["lng"], df["lat"]), crs=4326)
        within = gpd.sjoin(pts, urban_kind, predicate="within", how="inner").drop_duplicates("i")
        df.loc[within["i"].to_numpy(), "uc_id"] = within["uc_id"].to_numpy()
    return df.sort_values("h3").reset_index(drop=True)

def run(settings: Settings) -> dict[int, int]:
    settings.ensure_dirs()
    path = land_path(settings)
    if not path.exists():
        raise FileNotFoundError(f"land polygons not fetched: {path} (run `fetch` first)")
    sources = load_sources(settings.sources_path)
    adm0_path = settings.raw(ADM0_SOURCE) / sources[ADM0_SOURCE].files[0]
    counts: dict[int, int] = {}
    land = adm0 = urban = None
    def _land():
        nonlocal land
        if land is None:
            land = gpd.read_file(path)
            if land.crs is not None and land.crs.to_epsg() != 4326: land = land.to_crs(4326)
            if settings.bbox: land = gpd.clip(land, box(*settings.bbox))
        return land
    for res in settings.res:
        entry = settings.plan.entry(res)
        out = settings.hexes_path(res)
        inputs = [path]
        if not entry.complete:
            parent_path = settings.hexes_path(entry.parent)
            if not parent_path.exists():
                raise FileNotFoundError(f"{parent_path} missing: run grid for res {entry.parent} first (res {res} is built from its cells)")
            inputs.append(parent_path)
            if "urban" in entry.where:
                if not settings.urban_path.exists():
                    raise FileNotFoundError(f"{settings.urban_path} missing: run `urban` first (res {res} refines urban {entry.where['urban']}s)")
                inputs.append(settings.urban_path)
            if "countries" in entry.where:
                inputs.append(adm0_path)
        params = {"res": res, "bbox": settings.bbox, "stage": "grid", "plan": entry.to_manifest(), "iso_overrides": settings.iso_overrides}
        if stage_cache.is_fresh(out, inputs, params, settings.force):
            n = len(pd.read_parquet(out, columns=["h3"])); print(f"grid   res {res}: up to date ({n} hexes), skipping"); counts[res] = n; continue
        t0 = time.time()
        if entry.complete:
            df = build_hexes(_land(), res)
        else:
            parents = pd.read_parquet(settings.hexes_path(entry.parent), columns=["h3", "lat", "lng"])
            if "urban" in entry.where and urban is None: urban = gpd.read_parquet(settings.urban_path)
            if "countries" in entry.where and adm0 is None: adm0 = gpd.read_file(adm0_path).to_crs(4326)
            df = refine(parents, entry, _land(), urban, adm0, settings.iso_overrides)
        df.to_parquet(out, index=False)
        stage_cache.record(out, inputs, params, {"rows": len(df)})
        how = "land hexes" if entry.complete else f"children of res {entry.parent} ({entry.where})"
        print(f"grid   res {res}: {len(df)} {how} in {time.time() - t0:.1f}s -> {out.name}")
        counts[res] = len(df)
    return counts
```

`ADM0_SOURCE` import: move the constant to `grid.py` or keep in `admin.py` and import (no circularity: admin does not import grid). Every other stage already reads only `h3, lat, lng` from the hexes parquet; check `sanity.load_merged` and `export._typed` tolerate the extra `parent`/`uc_id` columns (they merge on `h3`; `export` must drop `parent`/`uc_id` from the tile attribute list, which `attrs.tile_attrs` already restricts).

- [ ] **Step 4: Run new tests + full suite (the res-4 tests must stay green), ruff, commit** — `git commit -m "grid: build derived resolutions from the plan (children of parents matching country / urban rules)"`

---

### Task 7: Reference-distribution scoring and joiner direction

**Files:**
- Create: `pipeline/reference.py`, `tests/test_reference.py`
- Modify: `pipeline/scoring.py`, `pipeline/stages/hazards.py:120-175`, `pipeline/stages/score.py`, `pipeline/registry.py:71-107` (`JoinSpec.higher_is`), `pipeline/manifest.py:27` (processing note)
- Test: `tests/test_scoring.py`, `tests/test_score.py`

**Interfaces:** `scoring.percentile_score(values, domain, reference: np.ndarray | None = None)`; `scoring.minmax_score(values, group, reference: pd.DataFrame | None = None)` (`reference` columns `v, g`); `scoring.bivariate_cuts(exposure, wb, inhabited) -> tuple[np.ndarray, np.ndarray] | None`; `scoring.bivariate_class(exposure, wb, inhabited, cuts=None)`; `reference.reference_frame(settings, res) -> pd.DataFrame | None` (inhabited rows of the reference res, every stage that exists merged); `reference.reference_inputs(settings, res, stages: tuple[str, ...]) -> list[Path]`; `reference.require(frame, column, stage, ref_res)` raises `FileNotFoundError("run <stage> for res <ref> first")`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_scoring.py
def test_percentile_against_a_reference_distribution():
    values = pd.Series([1.0, 5.0, 10.0]); domain = pd.Series([True, True, True])
    ref = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])
    got = percentile_score(values, domain, reference=ref).tolist()
    assert got == [17, 50, 92]          # midrank of 1, 5 and 10 among the six reference values
    assert percentile_score(values, domain, reference=np.array([])).isna().all()

def test_minmax_against_reference_bounds():
    ref = pd.DataFrame({"v": [0.2, 0.8], "g": ["shdi", "shdi"]})
    got = minmax_score(pd.Series([0.5, 0.9]), pd.Series(["shdi", "shdi"]), reference=ref).tolist()
    assert got == [50, 100]             # clipped at the reference maximum

def test_bivariate_cuts_round_trip():
    e = pd.Series([10.0, 50.0, 90.0, 20.0]); w = pd.Series([90.0, 50.0, 10.0, 80.0]); inh = pd.Series([True] * 4)
    cuts = bivariate_cuts(e, w, inh)
    assert bivariate_class(e, w, inh, cuts=cuts).tolist() == bivariate_class(e, w, inh).tolist()

# tests/test_reference.py
def test_derived_resolution_scores_use_the_res5_distribution(settings):
    settings.res = [4, 5, 6, 7]
    for stage in (fetch, urban, grid, pop, admin, hazards, dims, score): stage.run(settings)
    r5 = sanity.load_merged(settings, 5); r7 = sanity.load_merged(settings, 7)
    ref = np.sort(r5.loc[r5["inhabited"] & r5["heat_ok"], "heat_days"].to_numpy())
    row = r7[r7["heat_ok"]].iloc[0]
    expect = round(100 * (np.searchsorted(ref, row["heat_days"], "left") + np.searchsorted(ref, row["heat_days"], "right")) / (2 * len(ref)))
    assert int(row["heat_score"]) == expect
    assert r7["jobs_score"].dropna().between(0, 100).all() and r7["bivar"].isin(range(10)).all()

def test_missing_reference_is_a_plain_error(settings):
    settings.res = [4, 5, 6]
    for stage in (fetch, urban, grid, pop, admin): stage.run(settings)
    settings.res = [6]
    with pytest.raises(FileNotFoundError, match="run hazards for res 5 first"):
        hazards.run(settings)

def test_empty_reference_domain_leaves_scores_missing(settings):
    # A derived hex whose domain has no reference value: score stays NA, never 0. Simulated by
    # blanking the `uk` domain out of the res-5 dims parquet before scoring res 6.
    settings.res = [4, 5, 6]
    for stage in (fetch, urban, grid, pop, admin, hazards, dims): stage.run(settings)
    p5 = settings.stage_path("dims", 5); d5 = pd.read_parquet(p5)
    d5.loc[d5["jobs_dom"] == "uk", ["jobs_raw", "jobs_dom", "jobs_lbl"]] = [np.nan, None, None]
    d5.to_parquet(p5, index=False)
    score.run(settings)
    r6 = sanity.load_merged(settings, 6)
    assert (r6["jobs_dom"] == "uk").any()
    assert r6.loc[r6["jobs_dom"] == "uk", "jobs_score"].isna().all()

# tests/test_score.py
def test_opposite_direction_joiner_is_reflected():
    # a dimension higher_is better with joiner higher_is worse: raw 10 (worst) must score below raw 1
    dim = Dimension(id="d", name="d", group="life", kind="score", higher_is="better", joiners=[JoinSpec(source="s", joiner="polygon_centroid", res="tract", field="f", domain="x", label="imd", higher_is="worse")])
    df = pd.DataFrame({"d_raw": [1.0, 10.0, 5.0], "d_dom": ["x"] * 3, "d_lbl": ["imd"] * 3, "inhabited": [True] * 3})
    s = score_dimension(dim, df)["d_score"].tolist()
    assert s[0] > s[2] > s[1]
```

(`test_empty_reference_domain_leaves_scores_missing` runs res 5 then res 6 with `settings.bbox = (10, 40, 12, 44)`, after Task 9 wires the `uk` joiners; write it now with `pytest.mark.skipif` on the `eng_imd_2025` dimension entry existing, remove the skip in Task 9.)

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement**

`scoring.py`:

```python
def percentile_score(values, domain, reference: np.ndarray | None = None) -> pd.Series:
    """... `reference`: when given, the sorted-able array the scores are ranked against instead of
    values[domain] (SPEC §13.32: a res-7 hex is ranked among inhabited res-5 hexes so its colour
    means the same at every zoom). Empty reference -> all null."""
    v = pd.to_numeric(values, errors="coerce").astype("float64")
    has = v.notna().to_numpy()
    if reference is not None:
        dom = np.sort(np.asarray(reference, dtype="float64")); dom = dom[np.isfinite(dom)]
    else:
        dom = np.sort(v.to_numpy()[domain.to_numpy(dtype=bool) & has])
    ... (rest unchanged)

def minmax_score(values, group, reference: pd.DataFrame | None = None) -> pd.Series:
    """... `reference` (columns v, g): per-group lo/hi taken from that frame's distinct values;
    groups absent from it fall back to their own range."""
    bounds = {}
    if reference is not None:
        for g, sub in reference.dropna(subset=["v", "g"]).groupby("g", sort=False):
            u = sub["v"].unique(); bounds[g] = (float(u.min()), float(u.max()))
    ... inside the loop: lo, hi = bounds.get(g, (float(uniq.min()), float(uniq.max())))

def bivariate_cuts(exposure, wb, inhabited) -> tuple[np.ndarray, np.ndarray] | None:
    e, w = _num(exposure), _num(wb)
    dom = (e.notna() & w.notna() & inhabited.astype(bool)).to_numpy()
    if dom.sum() == 0: return None
    q = [100.0 / 3.0, 200.0 / 3.0]
    return np.nanpercentile(e.to_numpy()[dom], q), np.nanpercentile(w.to_numpy()[dom], q)

def bivariate_class(exposure, wb, inhabited, cuts=None) -> pd.Series:
    cuts = cuts if cuts is not None else bivariate_cuts(exposure, wb, inhabited)
    ... use np.searchsorted(cuts[0], e, side="right") / cuts[1]
```

`pipeline/reference.py`:

```python
"""Reference distributions for derived resolutions (SPEC §13.32)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from . import sanity
from .config import Settings

def reference_inputs(settings: Settings, res: int, stages: tuple[str, ...]) -> list[Path]:
    ref = settings.plan.reference_res(res)
    if ref is None: return []
    return [settings.hexes_path(ref)] + [settings.stage_path(s, ref) for s in stages]

def reference_frame(settings: Settings, res: int) -> pd.DataFrame | None:
    ref = settings.plan.reference_res(res)
    if ref is None: return None
    if not settings.stage_path("pop", ref).exists():
        raise FileNotFoundError(f"reference for res {res}: run pop for res {ref} first")
    df = sanity.load_merged(settings, ref)
    return df[df["inhabited"].fillna(False).astype(bool)].reset_index(drop=True)

def require(frame: pd.DataFrame | None, column: str, stage: str, settings: Settings, res: int) -> None:
    if frame is not None and column not in frame.columns:
        raise FileNotFoundError(f"reference for res {res}: run {stage} for res {settings.plan.reference_res(res)} first")
```

`hazards.py` (inside the res loop, before the cache check): `ref = reference.reference_frame(settings, res)`; `inputs += reference.reference_inputs(settings, res, ("pop", "hazards"))`; `params["reference_res"] = settings.plan.reference_res(res)`; scoring: `reference.require(ref, f"{hz}_ok", "hazards", settings, res)`; `r = None if ref is None else ref.loc[ref[f"{hz}_ok"].fillna(False).astype(bool), HAZARDS[hz][1]].to_numpy()`; `df[f"{hz}_score"] = percentile_score(raw, hexes["inhabited"] & df[f"{hz}_ok"], reference=r)`.

`score.py`: `score_dimension(dim, df, ref=None)`: minmax → `reference = None if ref is None else pd.DataFrame({"v": ref[f"{dim.id}_raw"], "g": ref[f"{dim.id}_lbl"]})`; percentile per domain → `r = None if ref is None else pd.to_numeric(ref.loc[ref[f"{dim.id}_dom"] == d, f"{dim.id}_raw"], errors="coerce").dropna().to_numpy()`; then the reflection:

```python
    flip = {j.label for j in dim.joiners if j.higher_is and j.higher_is != dim.higher_is}
    if flip and f"{dim.id}_lbl" in df.columns:
        m = df[f"{dim.id}_lbl"].isin(flip).to_numpy() & score.notna().to_numpy()
        score[m] = 100 - score[m]
```

In `run`: `ref = reference.reference_frame(settings, res)`; `reference.require(ref, f"{WB_ID}_raw", "dims", ...)` and `require(ref, "bivar", "score", ...)`; `cuts = None if ref is None else bivariate_cuts(ref["exposure"].astype("float64"), ref["wb_score"].astype("float64"), pd.Series(True, index=ref.index))`; inputs += `reference_inputs(settings, res, ("pop", "dims", "score"))`; params `reference_res`.

`registry.py`: `JoinSpec.higher_is: str | None = None`; parse `j.get("higher_is")`, validate `in (None, "better", "worse")`; include in `to_manifest()`.

`manifest.PROCESSING_NOTES[4]`: "... at the same H3 resolution; a derived resolution (res 6, 7) is ranked against the inhabited hexes of the finest complete resolution (res 5) in the same domain, so a neighbourhood keeps its colour meaning at every zoom. A joiner whose raw value runs opposite to its dimension (IMD deprivation feeding jobs) has its percentile reflected so every score obeys the dimension's stated direction."

- [ ] **Step 4: Tests, ruff, commit** — `git commit -m "scoring: derived resolutions rank against the res-5 reference distribution; joiner higher_is reflection (SPEC §13.32-33)"`

---

### Task 8: Export `ref`, manifest plan, per-archive tiles, publish

**Files:**
- Modify: `pipeline/attrs.py:14`, `pipeline/stages/export.py`, `pipeline/manifest.py:96-150`, `pipeline/stages/tiles.py` (whole file), `pipeline/tiler.py:141-165` (assertion), `pipeline/stages/publish.py:30,...`, `pipeline/__main__.py:120-138`
- Test: `tests/test_export.py`, `tests/test_tiler.py`, `tests/test_publish.py`

**Interfaces:** `manifest["resolution_plan"]: list[{res, fill, parent, where, zooms, archive, slim_below_zoom, complete, cells}]`; `manifest["tiles"][archive] = {key, sha256, bytes, backend, minzoom, maxzoom, layers: [{name, res, minzoom, maxzoom, complete, overzoom, features, fields, slim_below_zoom, description}]}`; `tiles.layer_specs(settings) -> dict[str, list[tiler.LayerSpec]]` (`LayerSpec` gains `res: int`, `complete: bool`, `overzoom: bool`); `tiles.run(settings, backend="auto", workers=None, archive=None)`; `publish.files_to_ship(manifest) -> list[str]`.

- [ ] **Step 1: Failing tests**

```python
# tests/test_export.py
def test_export_marks_refined_parents_and_writes_the_plan(settings):
    settings.res = [4, 5, 6, 7]
    run_everything_through(export)  # helper: fetch, urban, grid, pop, admin, hazards, dims, score, export
    r5 = pd.read_parquet(settings.out_dir / "hexes_r5.parquet"); r6 = pd.read_parquet(settings.hexes_path(6))
    assert r5["ref"].dtype == "boolean" and set(r5.loc[r5["ref"].fillna(False), "h3"]) == set(r6["parent"])
    assert not (r5["ref"] == False).any()                            # never False: only True or missing (invariant 3)
    r7 = pd.read_parquet(settings.out_dir / "hexes_r7.parquet")
    assert "ref" not in r7.columns or r7["ref"].isna().all()
    m = json.loads((settings.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert [e["res"] for e in m["resolution_plan"]] == [4, 5, 6, 7] and m["resolution_plan"][3]["cells"] == len(r7)

# tests/test_tiler.py
def test_tiles_build_one_archive_per_plan_entry(settings):
    settings.res = [4, 5, 6, 7]; run_everything_through(export)
    info = tiles.run(settings, backend="python", workers=0)
    m = manifest.load(settings)
    assert set(m["tiles"]) == {"hexes", "hexes_fine"}
    fine = {L["name"]: L for L in m["tiles"]["hexes_fine"]["layers"]}
    assert fine["hex6"]["minzoom"] == 8 and fine["hex6"]["maxzoom"] == 9 and fine["hex7"]["overzoom"] and not fine["hex6"]["complete"]
    coarse = {L["name"]: L for L in m["tiles"]["hexes"]["layers"]}
    assert coarse["hex5"]["overzoom"] and not coarse["hex4"]["overzoom"] and coarse["hex4"]["complete"]
    assert (settings.out_dir / "hexes_fine.pmtiles").stat().st_size > 1000
    # the z7 tile over Alder carries hex5 features with ref true; the z10 tile carries hex7 features without ref
    from pmtiles.reader import MmapSource, Reader
    import mapbox_vector_tile, gzip
    def _features(archive, z, lng, lat, layer):
        x, y = tiler.lnglat_to_tile(lng, lat, z)
        with open(settings.out_dir / archive, "rb") as fh:
            data = Reader(MmapSource(fh)).get(z, x, y)
        return mapbox_vector_tile.decode(gzip.decompress(data))[layer]["features"]
    assert any(f["properties"].get("ref") is True for f in _features("hexes.pmtiles", 7, 11.0, 43.0, "hex5"))
    assert all("ref" not in f["properties"] for f in _features("hexes_fine.pmtiles", 10, 11.0, 43.0, "hex7"))

def test_only_res4_still_overzooms(settings):
    settings.res = [4]; run_everything_through(export); tiles.run(settings, backend="python", workers=0)
    L = manifest.load(settings)["tiles"]["hexes"]["layers"]
    assert len(L) == 1 and L[0]["overzoom"]

def test_tiles_without_a_plan_in_the_manifest_is_a_plain_error(settings):
    settings.res = [4]; run_everything_through(export)
    m = manifest.load(settings); m.pop("resolution_plan"); manifest.write(settings, m)
    with pytest.raises(FileNotFoundError, match="run `export` first"):
        tiles.run(settings, backend="python", workers=0)

# tests/test_publish.py
def test_local_publish_ships_every_archive(settings, tmp_path):
    ... after tiles: publish.run(settings, target="local", local_dir=tmp_path / "data")
    assert {p.name for p in (tmp_path / "data").iterdir()} == {"hexes.pmtiles", "hexes_fine.pmtiles", "manifest.json"}
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement**

`attrs.BASE_ATTRS += ["ref"]`; `style_attrs` adds `"ref"`.

`export.py`: after `_typed(df)` for res r: `child = settings.plan.next_finer(r)`; if child and `settings.hexes_path(child.res).exists()`: `parents = set(pd.read_parquet(settings.hexes_path(child.res), columns=["parent"])["parent"])`; `df["ref"] = pd.array(np.where(df["h3"].isin(parents), True, pd.NA), dtype="boolean")`; add that path to the stage inputs so a rebuilt child invalidates the parent's export. Drop `parent`, `uc_id` from the out parquet? Keep them (parquet only; `tile_attrs` never lists them).

`manifest.build`: `manifest["resolution_plan"] = [{**e.to_manifest(), "cells": n_or_None} for e in settings.plan.entries]` where `cells = len(hexes parquet)` when it exists.

`tiles.py`:

```python
def layer_specs(settings: Settings) -> dict[str, list[tiler.LayerSpec]]:
    """Per archive, the layers to build, with zooms from the manifest's resolution plan (SPEC §9.1)."""
    m = manifest.load(settings)
    plan_rows = m.get("resolution_plan")
    if not plan_rows:
        raise FileNotFoundError("manifest.json has no resolution_plan: run `export` first")
    dims = load_dimensions(settings.dimensions_path, load_sources(settings.sources_path))
    full, slim = tuple(attrs.tile_attrs(dims)), tuple(attrs.style_attrs(dims))
    present = [r for r in plan_rows if r["res"] in settings.res and (settings.out_dir / f"hexes_r{r['res']}.parquet").exists()]
    if not present:
        raise FileNotFoundError(f"no data/out/hexes_r*.parquet for res {settings.res} (run `export` first)")
    by_archive: dict[str, list[tiler.LayerSpec]] = {}
    for i, row in enumerate(present):
        finer = present[i + 1:]
        overzoom = not finer or not finer[0]["complete"]   # a coarse layer keeps drawing where no complete finer layer exists
        by_archive.setdefault(row["archive"], []).append(tiler.LayerSpec(
            name=f"hex{row['res']}", parquet=settings.out_dir / f"hexes_r{row['res']}.parquet",
            minzoom=row["zooms"][0], maxzoom=row["zooms"][1], attrs=full, slim_attrs=slim,
            slim_below_zoom=row.get("slim_below_zoom"), res=row["res"], complete=row["complete"], overzoom=overzoom,
            description=f"H3 resolution {row['res']} hexes (SPEC §6.1 attributes)"))
    return by_archive

def run(settings, backend="auto", workers=None, archive=None) -> dict:
    ... for name, specs in layer_specs(settings).items():
        if archive and name != archive: continue
        out = settings.out_dir / f"{name}.pmtiles"; inputs = [s.parquet for s in specs]; params = {... "archive": name, "zooms": [(s.name, s.minzoom, s.maxzoom, s.slim_below_zoom, s.overzoom) for s in specs] ...}
        cache / build as today (tippecanoe path unchanged apart from the per-archive `out`)
        m["tiles"][name] = {"key": f"{name}.pmtiles", "sha256":..., "bytes":..., "backend": chosen, "minzoom": ..., "maxzoom": ..., "layers": [{**L, "res": s.res, "complete": s.complete, "overzoom": s.overzoom} for L, s in zip(info["layers"], specs)]}
```

`tiler.LayerSpec` fields `res: int = 0`, `complete: bool = True`, `overzoom: bool = False`. In `build_pmtiles`, before `assign_tiles`: `span = (bbox[:, 2] - bbox[:, 0]).max() * (1 << z); if span > 2: raise ValueError(f"{spec.name} at z{z}: a hex spans {span:.1f} tiles; the tiler assumes at most 3x3")`. `__main__.tiles`: drop `--maxzoom`, add `--archive`. Delete `MIN_ZOOM`, `LAYER_ZOOMS`, `SLIM_BELOW`.

`publish.py`: `def files_to_ship(m: dict) -> list[str]: return ["manifest.json"] + sorted(t["key"] for t in m.get("tiles", {}).values())`; replace uses of `FILES`; the R2 range check runs on every archive.

- [ ] **Step 4: Tests, ruff, `uv run python -m pipeline --fixtures all` (now builds res 4-7 and two archives; note its wall time in the commit message), commit** — `git commit -m "export/tiles/publish: ref flag, resolution plan in the manifest, one PMTiles archive per plan archive"`

---

### Task 9: Eurostat grid and England IMD loaders, `grid` tag, dimension joiners

**Files:**
- Create: `pipeline/prep/eurostat_grid.py`, `pipeline/prep/imd.py`
- Modify: `pipeline/config.py:22` (`RES_TAGS` + `grid`), `pipeline/registry.py:65,228-231` (`grid` allowed for the hex joiners), `pipeline/prep/__init__.py:26-50` (`PREP_VERSION = 7`, two `LOADERS` entries), `pipeline/dimensions.yaml` (jobs, health, house)
- Test: `tests/test_prep_loaders.py`, `tests/test_dims.py`, `tests/test_registry.py`

**Interfaces:** `eurostat_grid.load(settings, source, sources) -> pd.DataFrame[lat, lng, pop, pop_1564, emp, emp_rate, share_ge65]`; `eurostat_grid.parse_grd_id(series) -> (x, y)` (EPSG:3035 cell centres); `imd.load(settings, source, sources) -> gpd.GeoDataFrame[LSOA21CD, LSOA21NM, emp_dep_rate, health_dep, housing_barriers, income_dep_rate, imd_score, population, pop_working, geometry]`; `imd.COLUMNS: dict[str, str]` (our name -> File 7 header, exact strings from Task 1).

- [ ] **Step 1: Failing tests**

```python
# tests/test_prep_loaders.py
def test_eurostat_grd_id_parses_to_cell_centres():
    from pipeline.prep.eurostat_grid import parse_grd_id, to_wgs84
    x, y = parse_grd_id(pd.Series(["CRS3035RES1000mN2684000E4334000"]))
    assert x.tolist() == [4334500.0] and y.tolist() == [2684500.0]
    lat, lng = to_wgs84(x, y)
    assert 40 < lat[0] < 60 and -10 < lng[0] < 30

def test_eurostat_loader_on_a_synthetic_csv(tmp_path, settings):
    csv = tmp_path / "grid.csv"
    csv.write_text("GRD_ID,T,M,F,Y_LT15,Y_1564,Y_GE65,EMP,NAT,EU_OTH,OTH,SAME,CHG_IN,CHG_OUT\n"
                   "CRS3035RES1000mN2684000E4334000,100,50,50,20,60,20,30,90,5,5,80,10,10\n"
                   "CRS3035RES1000mN2685000E4334000,10,5,5,2,0,8,0,10,0,0,9,1,0\n", encoding="utf-8")
    df = eurostat_grid.load_csv(csv)
    assert df["emp_rate"].round(2).tolist()[0] == 0.5 and pd.isna(df["emp_rate"].iloc[1])   # no working-age population -> NaN, not 0

def test_imd_loader_joins_scores_to_lsoas(tmp_path):
    from pipeline.prep import imd
    header = ",".join(f'"{h}"' for h in imd.COLUMNS.values())
    (tmp_path / "f7.csv").write_text(header + "\nE01000001,25.5,0.2,0.1,0.5,20.0,1600,950\n", encoding="utf-8")
    gpd.GeoDataFrame({"LSOA21CD": ["E01000001", "W01000001"], "LSOA21NM": ["City 001A", "Cardiff 001A"]},
                     geometry=[box(0, 51, 0.01, 51.01), box(-3.2, 51.4, -3.19, 51.41)], crs=4326).to_file(tmp_path / "lsoa.geojson", driver="GeoJSON")
    out = imd.load_frames(tmp_path / "f7.csv", tmp_path / "lsoa.geojson")
    assert len(out) == 2 and out.set_index("LSOA21CD").loc["E01000001", "emp_dep_rate"] == 0.1
    assert out.set_index("LSOA21CD").loc["W01000001", ["emp_dep_rate", "health_dep", "housing_barriers"]].isna().all()

# tests/test_registry.py
def test_grid_tag_allowed_only_for_hex_joiners(tmp_path, settings):
    sources = load_sources(settings.sources_path)
    ok = {"id": "g", "name": "g", "group": "life", "kind": "score", "sources": ["acag_pm25"], "joiners": [{"source": "acag_pm25", "joiner": "raster_mean", "res": "grid", "field": "value", "domain": "global", "label": "x"}]}
    bad = {**ok, "joiners": [{"source": "acs_summary", "joiner": "area_weighted_overlay", "res": "grid", "field": "f", "domain": "us", "label": "x"}]}
    p = tmp_path / "dims.yaml"
    p.write_text(yaml.safe_dump([ok]), encoding="utf-8"); assert "g" in load_dimensions(p, sources)
    p.write_text(yaml.safe_dump([bad]), encoding="utf-8")
    with pytest.raises(ValueError, match="hex"):
        load_dimensions(p, sources)

# tests/test_dims.py
def test_grid_and_imd_joiners_fill_the_fixture_regions(settings):
    settings.res = [4, 5, 6]; run fetch, urban, grid, pop, admin, dims
    d6 = sanity.load_merged(settings, 6)
    xa = d6[d6["iso_a2"] == "XA"]; bmid = d6[(d6["lng"] > 12) & (d6["lat"].between(41.5, 43))]
    assert (xa["jobs_res"] == "grid").mean() > 0.8 and (xa["jobs_dom"] == "eu").any()
    assert (bmid["jobs_res"] == "tract").mean() > 0.5 and (bmid["health_res"] == "tract").any() and (bmid["house_res"] == "tract").any()
    assert d6.loc[d6["jobs_res"] == "grid", "jobs_raw"].between(0.3, 0.9).all()
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement**

`config.RES_TAGS = ("hex", "grid", "basin", "admin1", "county", "tract", "national", "none")`. `registry.py`: `HEX_TAGS = ("hex", "grid")`; the two checks become "`raster_mean`/`point_mean` must carry `hex` or `grid`" and "only those joiners may carry `hex` or `grid`".

`pipeline/prep/eurostat_grid.py`:

```python
"""Eurostat Census 2021 1 km grid (SPEC §20.6, §15): GRD_ID -> WGS84 cell centre, counts -> rates."""
from __future__ import annotations
import re, zipfile
import numpy as np
import pandas as pd
from pyproj import Transformer

_ID = re.compile(r"CRS3035RES1000mN(\d+)E(\d+)")
NEEDED = ["GRD_ID", "T", "Y_1564", "Y_GE65", "EMP"]

def parse_grd_id(ids: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    parts = ids.str.extract(_ID)
    y = parts[0].astype("float64").to_numpy() + 500.0
    x = parts[1].astype("float64").to_numpy() + 500.0
    return x, y

def to_wgs84(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lng, lat = Transformer.from_crs(3035, 4326, always_xy=True).transform(x, y)
    return np.asarray(lat), np.asarray(lng)

def load_csv(path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(path_or_buffer, usecols=lambda c: c in NEEDED or c.endswith("_CI"), dtype={"GRD_ID": str})
    for col in ("T", "Y_1564", "Y_GE65", "EMP"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        ci = f"{col}_CI"   # confidentiality flag column, if the file has one (Task 1 records the real name)
        if ci in df.columns:
            df.loc[pd.to_numeric(df[ci], errors="coerce").fillna(0) > 0, col] = np.nan
    x, y = parse_grd_id(df["GRD_ID"]); lat, lng = to_wgs84(x, y)
    den = df["Y_1564"].where(df["Y_1564"] > 0)
    return pd.DataFrame({"lat": lat, "lng": lng, "pop": df["T"], "pop_1564": df["Y_1564"], "emp": df["EMP"],
                         "emp_rate": (df["EMP"] / den).clip(0, 1), "share_ge65": (df["Y_GE65"] / df["T"].where(df["T"] > 0)).clip(0, 1)})

def load(settings, source, sources) -> pd.DataFrame:
    raw = settings.raw(source.id) / source.files[0]
    with zipfile.ZipFile(raw) as zf, zf.open(source.extra["member"]) as fh:
        return load_csv(fh)
```

`pipeline/prep/imd.py`:

```python
"""English Indices of Deprivation 2025 File 7 joined to ONS LSOA 2021 boundaries (SPEC §20.6, §15)."""
COLUMNS = {  # our column -> File 7 header (exact strings recorded in SPEC §15 by Task 1)
    "LSOA21CD": "LSOA code (2021)",
    "imd_score": "Index of Multiple Deprivation (IMD) Score",
    "income_dep_rate": "Income Score (rate)",
    "emp_dep_rate": "Employment Score (rate)",
    "health_dep": "Health Deprivation and Disability Score",
    "housing_barriers": "Barriers to Housing and Services Score",
    "population": "Total population: mid 2022 (excluding prisoners)",
    "pop_working": "Working age population 18-59/64: for use with Employment Deprivation Domain (excluding prisoners)",
}

def load_frames(csv_path, geo_path) -> gpd.GeoDataFrame:
    scores = pd.read_csv(csv_path, usecols=list(COLUMNS.values()), encoding="utf-8-sig").rename(columns={v: k for k, v in COLUMNS.items()})
    lsoa = gpd.read_file(geo_path)[["LSOA21CD", "LSOA21NM", "geometry"]].to_crs(4326)
    out = lsoa.merge(scores, on="LSOA21CD", how="left")   # Welsh LSOAs stay NaN: IMD is England only
    for c in ("imd_score", "income_dep_rate", "emp_dep_rate", "health_dep", "housing_barriers", "population", "pop_working"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out

def load(settings, source, sources) -> gpd.GeoDataFrame:
    geo = sources[source.extra["geometry"]]
    return load_frames(settings.raw(source.id) / source.files[0], settings.raw(geo.id) / geo.files[0])
```

If Task 1 found different header strings, `COLUMNS` follows Task 1. Missing header → `KeyError` becomes a plain "File 7 column '...' not found; the IoD2025 headers may have changed (SPEC §15)".

`dimensions.yaml`:

```yaml
# jobs, after the acs joiner
    - {source: eurostat_census_grid_2021, joiner: point_mean, res: grid, field: emp_rate, weight_field: pop_1564, domain: eu, label: eugrid, unit: "% employed (ages 15-64)", multiply: 100, decimals: 0}
    - {source: eng_imd_2025, joiner: area_weighted_overlay, res: tract, field: emp_dep_rate, weight_field: pop_working, domain: uk, label: imd, higher_is: worse, unit: "% employment-deprived (working age; IoD2025, higher = worse)", multiply: 100, decimals: 0}
# health, before the oecd joiner
    - {source: eng_imd_2025, joiner: area_weighted_overlay, res: tract, field: health_dep, weight_field: population, domain: uk, label: imd, higher_is: worse, unit: "health deprivation score (IoD2025, higher = worse)", decimals: 2}
# house, before the oecd joiner (same direction as the dimension: higher = worse)
    - {source: eng_imd_2025, joiner: area_weighted_overlay, res: tract, field: housing_barriers, weight_field: population, domain: uk, label: imd, unit: "barriers to housing and services score (IoD2025, higher = worse)", decimals: 1}
```

Add the sources to each dimension's `sources:` list (`eurostat_census_grid_2021`; `eng_imd_2025, ons_lsoa_2021`), extend `coverage:` with `eu` / `uk`, and the `note:` text. `LOADERS["eurostat_census_grid_2021"] = "pipeline.prep.eurostat_grid:load"`, `LOADERS["eng_imd_2025"] = "pipeline.prep.imd:load"`, `PREP_VERSION = 7`. `dims._layer_mask` already keeps the LSOA overlay to England's bbox; `point_mean` handles the grid points globally.

- [ ] **Step 4: Remove the skip from Task 7's empty-domain test; tests, ruff, commit** — `git commit -m "dims: Eurostat 1 km census grid (jobs, tag grid) and English IoD 2025 (jobs, health, house at LSOA)"`

---

### Task 10: Web: manifest-driven layers, two sources, refined-parent hiding, labels

**Files:**
- Create: `web/src/lib/layers.ts`, `web/src/lib/layers.test.ts`
- Modify: `web/src/lib/manifest.ts:6,11,67-85`, `web/src/lib/style.ts`, `web/src/lib/style.test.ts`, `web/src/lib/inspect.ts:118`, `web/src/lib/inspect.test.ts`, `web/src/lib/dims.ts:88-107,142`, `web/src/lib/format.ts` (grid unit fallback), `web/src/lib/config.ts:20-24`, `web/src/components/MapView.tsx`, `web/src/components/MapApp.tsx:113-139`, `web/src/components/Inspector.tsx:32`, `web/src/app/methodology/page.tsx:11`, `web/smoke/index.html:58-64`

**Interfaces:** `layers.TileLayer { name; source; minzoom; maxzoom; res; complete; overzoom }`; `layers.tileLayersFrom(tiles: Manifest["tiles"] | undefined): TileLayer[]`; `layers.archivesFrom(tiles): { id: string; key: string }[]`; `layers.DEFAULT_TILE_LAYERS`; `style.buildLayers(o, showUninhabited, conf, tileLayers)` unchanged signature, `style.hexSourceIds(layers)`; `MapView` props `archives: {id, key}[]` replaces `tilesKey`.

- [ ] **Step 1: Failing tests**

```ts
// layers.test.ts
const TILES = {
  hexes: { key: "hexes.pmtiles", sha256: "", bytes: 1, minzoom: 2, maxzoom: 7, layers: [
    { name: "hex4", minzoom: 2, maxzoom: 4, res: 4, complete: true, overzoom: false },
    { name: "hex5", minzoom: 5, maxzoom: 7, res: 5, complete: true, overzoom: true } ] },
  hexes_fine: { key: "hexes_fine.pmtiles", sha256: "", bytes: 1, minzoom: 8, maxzoom: 13, layers: [
    { name: "hex7", minzoom: 10, maxzoom: 13, res: 7, complete: false, overzoom: true },
    { name: "hex6", minzoom: 8, maxzoom: 9, res: 6, complete: false, overzoom: true } ] },
};
it("orders layers by resolution across archives and keeps their source", () => {
  const L = tileLayersFrom(TILES);
  expect(L.map((l) => l.name)).toEqual(["hex4", "hex5", "hex6", "hex7"]);
  expect(L[2].source).toBe("hexes_fine");
  expect(archivesFrom(TILES)).toEqual([{ id: "hexes", key: "hexes.pmtiles" }, { id: "hexes_fine", key: "hexes_fine.pmtiles" }]);
});
it("falls back to hex4/hex5 for a manifest without flags", () => {
  const L = tileLayersFrom({ hexes: { key: "hexes.pmtiles", sha256: "", bytes: 1, minzoom: 2, maxzoom: 7, layers: [{ name: "hex4", minzoom: 2, maxzoom: 4 }, { name: "hex5", minzoom: 5, maxzoom: 7 }] } });
  expect(L[1]).toMatchObject({ res: 5, complete: true, overzoom: true, source: "hexes" });
  expect(tileLayersFrom(undefined)).toEqual(DEFAULT_TILE_LAYERS);
});

// style.test.ts (extend)
it("overzooms per manifest flag and hides refined parents from the next layer's minzoom", () => {
  const layers = buildLayers(OPTS, false, true, tileLayersFrom(TILES));
  const fill5 = layers.find((l) => l.id === "fill-hex5")!, fill6 = layers.find((l) => l.id === "fill-hex6")!, fill4 = layers.find((l) => l.id === "fill-hex4")!;
  expect(fill4.maxzoom).toBe(5); expect(fill5.maxzoom).toBeUndefined(); expect(fill6.maxzoom).toBeUndefined();
  expect(fill5.source).toBe("hexes"); expect(fill6.source).toBe("hexes_fine");
  expect(fill5.paint!["fill-opacity"]).toEqual(["step", ["zoom"], 0.85, 8, ["case", ["==", ["get", "ref"], true], 0, 0.85]]);
  expect(fill6.paint!["fill-opacity"]).toEqual(["step", ["zoom"], 0.85, 10, ["case", ["==", ["get", "ref"], true], 0, 0.85]]);
  expect(layers.find((l) => l.id === "fill-hex7")!.paint!["fill-opacity"]).toBe(0.85);
  expect(validateStyleMin(styleWith(layers)).length).toBe(0);
});
it("carries every hex source across a theme change", () => { ... expect(Object.keys(merged.sources)).toEqual(expect.arrayContaining(["hexes", "hexes_fine"])) });

// inspect.test.ts (extend)
it("labels the resolution from the res attribute", () => {
  expect(describeHex({ ...props, res: 7 }, "hex7", DIMS, MANIFEST).resolution).toBe("H3 res 7 hex (~5.2 km²)");
  expect(describeHex({ ...props }, "hex6", DIMS, MANIFEST).resolution).toBe("H3 res 6 hex (~36 km²)");
});
```

- [ ] **Step 2: Run `npm test`, expect failures**

- [ ] **Step 3: Implement**

`layers.ts`:

```ts
import type { Manifest } from "./manifest";
export interface TileLayer { name: string; source: string; minzoom: number; maxzoom: number; res: number; complete: boolean; overzoom: boolean }
export const DEFAULT_TILE_LAYERS: TileLayer[] = [
  { name: "hex4", source: "hexes", minzoom: 2, maxzoom: 4, res: 4, complete: true, overzoom: false },
  { name: "hex5", source: "hexes", minzoom: 5, maxzoom: 7, res: 5, complete: true, overzoom: true },
];
const resOf = (name: string) => Number(name.replace(/\D/g, "")) || 0;
export function tileLayersFrom(tiles: Manifest["tiles"] | undefined): TileLayer[] {
  const out: TileLayer[] = [];
  for (const [source, a] of Object.entries(tiles ?? {})) for (const l of a.layers ?? []) {
    out.push({ name: l.name, source, minzoom: l.minzoom, maxzoom: l.maxzoom, res: l.res ?? resOf(l.name), complete: l.complete ?? true, overzoom: l.overzoom ?? false });
  }
  if (!out.length) return DEFAULT_TILE_LAYERS;
  out.sort((a, b) => a.res - b.res);
  if (!out.some((l) => l.overzoom)) out[out.length - 1].overzoom = true; // old manifests: the top layer overzooms
  return out;
}
export const archivesFrom = (tiles: Manifest["tiles"] | undefined) => Object.entries(tiles ?? {}).map(([id, a]) => ({ id, key: a.key }));
```

`manifest.ts`: `TileLayerEntry { name; minzoom; maxzoom; res?; complete?; overzoom?; features?; slim_below_zoom?: number | null }`, `TileArchive { key; sha256; bytes; layers: TileLayerEntry[]; minzoom; maxzoom }`, `tiles: Record<string, TileArchive>`, `ResTag` + `"grid"`, `Domain` + `"eu" | "uk"`, `EMPTY_MANIFEST.tiles = {}`.

`style.ts`: import `TileLayer`/`DEFAULT_TILE_LAYERS` from `./layers` (re-export for callers); `zoomRange(l) = l.overzoom ? { minzoom: l.minzoom } : { minzoom: l.minzoom, maxzoom: l.maxzoom + 1 }`; `hideFrom(l, all) = min minzoom among layers with res > l.res, or undefined`; `opacity(base, from) = from === undefined ? base : ["step", ["zoom"], base, from, ["case", ["==", ["get", "ref"], true], 0, base]]`; use `source: tl.source`, `fill-opacity: opacity(0.85, from)`, hatch `opacity(0.5, from)`, and `line-opacity: opacity(1, from)` on national/hover/halo/selected. `hexSourceIds(layers) = [...new Set(layers.map((l) => l.source))]`; `mergeStyleOnThemeChange` copies every source referenced by a hex layer.

`MapView.tsx`: prop `archives: { id: string; key: string }[]`; `for (const a of archives) map.addSource(a.id, { type: "vector", url: \`pmtiles://${tilesUrl(a.key)}\`, promoteId: "h3" })`; hovered/selected keep `{ source: f.source, layer: f.sourceLayer, id }` and `setFeatureState({ source, sourceLayer, id }, ...)`; `MAP_MAX_ZOOM = 14` in config (remove `HEX_SPLIT_ZOOM`). `MapApp.tsx`: `tileLayers = tileLayersFrom(manifest.tiles)`, `archives = archivesFrom(manifest.tiles)`; `SelectedHex` gains `source`.

`inspect.ts`: `const HEX_AREA: Record<number, string> = { 4: "1,770", 5: "253", 6: "36", 7: "5.2", 8: "0.74", 9: "0.11", 10: "0.015" }`; `const r = num(p.res) ?? Number(sourceLayer.replace(/\D/g, "")) || 4; resolution: \`H3 res ${r} hex (~${HEX_AREA[r] ?? "?"} km²)\``.

Labels: `dims.RES_LABELS.grid = "1 km grid"`, `Inspector.RES_WORDS.grid = "grid cell (1 km)"`, `RES_WORDS.tract = "tract / small-area level"`; chip labels in `dims.chipFor`: `eu → "EU"`, `uk → "England"`; `format.unitFor("grid")` same fallback as `hex`; methodology `TAG_ORDER = ["hex", "grid", "basin", "tract", "county", "admin1", "national", "none"]`; smoke page lists the four layers.

- [ ] **Step 4: `npm test && npm run lint && npm run build`; then `uv run python -m pipeline --fixtures publish --target local && npm run dev` and check in the browser at z9 over Alder (hex6 drawn, hex5 parents gone, no doubled colour) and at z11 (hex7); commit** — `git commit -m "web: layers and sources from the manifest, refined parents hidden under finer layers, res 6/7 labels"`

---

### Task 11: SPEC, README, CLAUDE.md, manifest notes

**Files:** `SPEC.md` (§4 invariant 4.2, §5, §6.1, §9.1, §11, §13.31-34, §15 done in Task 1, §16 Session 8 row, §17 unchanged, §20.3, §20.6), `README.md` (§5 mirror), `CLAUDE.md` (status, commands: `urban`, `--archive`, plan file; architecture: resolution plan, reference scoring, `grid` tag, two archives), `pipeline/manifest.py` notes (grid note: "derived resolutions are the H3 children of parent cells matching the resolution plan; children whose centre is in the ocean are absent").

- [ ] **Step 1: §5 diagram** — add after `fetch`: `|  urban     GHS-SMOD classes -> urban centre / cluster polygons with ids -> data/interim/urban.parquet (§13.31)|`; `grid` line: `resolution plan (pipeline/resolution_plan.yaml): res 4-5 from land, res 6 children of parents in plan countries or touching urban clusters, res 7 inside urban centres`; `dims` tag list `'hex' | 'grid' | 'basin' | ...`; `tiles` line: `hexes.pmtiles (hex4 z2-4, hex5 z5-7) + hexes_fine.pmtiles (hex6 z8-9, hex7 z10-13 where built); coarse layers overzoom, refined parents hidden via ref (§9.1)`; R2 box lists both archives. Copy the diagram into README verbatim (fix the README's stale `dims`/`tiles` lines while there).
- [ ] **Step 2: §6.1** `res int 4-7 (resolution plan)`, `ref bool true when a finer layer covers this cell (absent otherwise; parquet also keeps parent, uc_id)`, tag list with `grid`.
- [ ] **Step 3: §9.1** table: layer, resolution, where, zooms, archive; the overzoom / `ref` rule; the notch caveat from D3.
- [ ] **Step 4: §11** placeholder lines for the Task 12 measurements (cells per res, stage timings, archive sizes) and the rule "each archive stays under ~300 MB; past that, split by plan `archive`".
- [ ] **Step 5: §13.31-34** from D2, D5-D7 (dated 2026-09-22); §16 Session 8 row status "Built (this PR)"; §20.3 `grid`; §20.6 rows for Eurostat grid and IoD2025 on jobs/health/house.
- [ ] **Step 6: Commit** — `git commit -m "docs: SPEC §5/§6.1/§9.1/§11/§13.31-34/§20 and README for neighbourhood resolution; CLAUDE.md status"`

---

### Task 12: Real-data build, measurements, PR

- [ ] **Step 1: Background run with logs** (each in its own Bash call with `run_in_background`, `PYTHONUNBUFFERED=1 PYTHONUTF8=1`, log under `data/interim/logs/`):

```bash
export PATH="$HOME/.local/bin:$PATH"; mkdir -p data/interim/logs
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline urban > data/interim/logs/urban.log 2>&1
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline --res 6 --res 7 grid > data/interim/logs/grid67.log 2>&1
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline --res 6 --res 7 pop > data/interim/logs/pop67.log 2>&1   # then admin, hazards, dims, score in turn
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline --res 4 --res 5 dims --only jobs --only health --only house > data/interim/logs/dims45_new.log 2>&1
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline --res 4 --res 5 score > data/interim/logs/score45.log 2>&1   # new reference values feed nothing at 4/5, but score reruns for the changed dims
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline export > data/interim/logs/export.log 2>&1
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline tiles > data/interim/logs/tiles.log 2>&1
PYTHONUNBUFFERED=1 PYTHONUTF8=1 uv run python -m pipeline publish --target local > data/interim/logs/publish.log 2>&1
```

Expected orders of magnitude: urban minutes; grid r6 ~400k cells, r7 ~350k; pop/hazards r6+r7 under an hour (windows outside the cell set are skipped); dims r6 several hours (US tract and block-group overlays: run overnight if needed); tiles ~30-60 min for `hexes_fine`. If `hexes_fine.pmtiles` exceeds ~300 MB, stop and split hex7 into a third archive in the plan before publishing.

- [ ] **Step 2: Sanity** — `uv run python -m pipeline --res 5 --res 6 --res 7 sanity`; spot-check three neighbourhoods in the browser (London at z11 should show hex7 with `jobs_res = tract` / `imd`; Berlin at z9 hex6 with `jobs_res = grid`; Lagos at z11 hex7 with global tags); confirm no doubled colour where hex6 meets hex5 at z8, and confirm `_score` values on a res-7 hex sit inside its res-5 parent's neighbourhood of values.
- [ ] **Step 3: Record §11** (cells per res, timings from `timings.json`, tile counts and archive sizes from `tiles_report.json`) and the SMOD polygon counts in §13.31; `python web/scripts/build_gazetteer.py` is not needed (places unchanged).
- [ ] **Step 4: Final checks** — `uv run pytest` (check exit status), `uv run ruff check .`, `uv run python -m pipeline --fixtures all`, `cd web && npm test && npm run lint && npm run build`; screenshots of z9 and z11 under `docs/screenshots/session-8/`.
- [ ] **Step 5: PR** — `git push -u origin claude/neighborhood`, `gh pr create --base main --title "Session 8: neighbourhood resolution (res 6/7, urban mask, Eurostat grid, England IoD 2025)" --body-file <scratch>` with a body listing the decisions (§13.31-34), measurements, what remains (Zensus 2022, CBS 100 m, IRIS, Canadian DAs, Australian SA2: one verification + loader each, `dims --only` to add them; R2 publish still needs `.env`). Update CLAUDE.md status line and the memory file `livability-map-session-plan.md`.

## Verification

- Unit and stage tests on the fixture world cover: plan validation, urban polygons (incl. window seams), children-of-parents grid with land filter and `uc_id`, aggregation on a cell subset equalling the full fill, reference percentiles equalling a hand computation, joiner reflection, `ref` in export, two archives with correct flags, the old-manifest fallbacks, Eurostat/IMD parsing on synthetic files, web layer/source/opacity expressions and labels.
- `uv run python -m pipeline --fixtures all` runs res 4-7 end to end in CI and writes two archives; `publish --target local` then `npm run dev` shows hex6/hex7 over Alder and Cedar with no gaps or doubled colour.
- The real run's §8.5 counts, spot checks and browser checks above, recorded in SPEC §11 before the PR is opened.

## Follow-ups (not in this PR)

Zensus 2022 100 m grid (dl-de/by-2-0), CBS 100 m vierkanten, INSEE IRIS + IGN contours, StatCan DAs + census profile, ABS SA2 + DataPacks: each a §15 verification, a `prep/<source>.py`, fixture stand-in, and joiner rows at tag `grid` or `tract`; add `CA`/`AU` to the plan's `countries` when their sources land. R2 publish of both archives once `.env` exists.
