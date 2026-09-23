# Session 8: Neighbourhood Resolution Design

Design approved 2026-09-22 (brainstorm with Saj). The implementation plan is
`docs/superpowers/plans/2026-09-22-session-8-neighbourhood-resolution.md`.

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

