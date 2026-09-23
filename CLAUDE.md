# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A global climate-livability map: projected climate hazard exposure (4 hazards, one scenario, 2050)
beside present-day wellbeing and user-weighted "life dimensions" on H3 hexes, built only from
open-licensed data. `SPEC.md` is the source of truth; build prompts and code comments cite its
section numbers (§5 architecture, §6 data model, §8 scoring, §13 decisions, §15 verification log,
§16 session plan, §20 life dimensions). Read it before changing anything structural, and update the
§5 ASCII diagram (mirrored in `README.md`) in the same change when the pipeline shape changes.

Two-language repo: `pipeline/` (Python 3.11+, Sessions 1-5) and `web/` (TypeScript, Sessions 6-7).
Status (2026-09-23): every stage and the map app run end to end on real data at H3 res 4 and 5
everywhere, res 6 across the US/EU/UK/EFTA and urban clusters, res 7 inside urban centres (Session
8, three PMTiles archives), with 18 dimensions incl. the Eurostat 1 km grid and England IoD 2025.
Country small-area / grid sources for DE, NL, FR, CA and AU are wired too (SPEC §13.35).
Outstanding: the R2/Pages publish (needs `.env` credentials) and three manual downloads (GDL SHDI,
MEDSL county returns, HUD FMR workbook). SPEC §13 records the decisions taken. A full res-6/7 rebuild takes ~8 hours.

## Commands

```bash
uv venv && uv pip install -e ".[dev]"            # one-time setup (Python 3.11+, uv)
uv run python -m pipeline --fixtures --res 4 all # full pipeline on the synthetic fixture world
uv run python -m pipeline --fixtures grid        # one stage; global options go BEFORE the stage name
uv run python -m pipeline --fixtures sanity      # SPEC §8.5 counts and spot checks
uv run pytest                                    # all tests (fixtures only, ~3 s)
uv run pytest tests/test_joiners.py -k overlay   # one test
uv run ruff check .                              # lint (line length 100, E501 ignored)
uv run python -m pipeline.fixtures.make_fixtures # regenerate fixtures (also happens lazily)
uv run python -m pipeline --res 4 all            # real data: fetch -> ... -> tiles -> publish (~35 min, 6 GB RAM)
uv run python -m pipeline --res 4 --bbox 89.5,23,91.5,25 hazards   # subregion run (own interim/out dirs)
uv run python -m pipeline --res 5 dims --only care --only net     # add layers without redoing the tract overlays
uv run python -m pipeline urban                                  # GHS-SMOD -> urban centre/cluster polygons
uv run python -m pipeline --res 6 --res 7 grid                   # derived resolutions from the plan (needs res 5 + urban)
uv run python -m pipeline tiles --archive hexes_nbhd             # one archive of the resolution plan
uv run python -m pipeline --fixtures --res 4 publish --target local  # -> web/public/data/
cd web && npm run dev | npm test | npm run lint | npm run build | npm run deploy
```

On this laptop `uv` lives in `~/.local/bin` (Git Bash: `export PATH="$HOME/.local/bin:$PATH"`)
and every script that writes repo files must use UTF-8 explicitly (`PYTHONUTF8=1`); the pipeline
code does.

CLI options (`--fixtures`, `--res`, `--bbox minlng,minlat,maxlng,maxlat`, `--force`) are typer
callback options and must precede the stage name. `--res` picks resolutions from the plan
(default: all of them). `all` runs stages in order and stops cleanly
at the first stage that is still planned (`pipeline/stages/PLANNED` maps stage to session).

## Environment constraint

The Claude Code cloud container blocks outbound HTTPS except to package registries and GitHub.
Real data sources cannot be fetched or verified first-hand here. Develop against the fixture world
(`--fixtures`); real fetches and the global build run on Saj's laptop. Every §15 entry marked
`search` still needs first-hand confirmation before `verified: confirmed` is set in
`pipeline/sources.yaml`.

## Architecture (the parts that span files)

**Settings flow.** `pipeline/__main__.py` builds one `config.Settings` and passes it to every
stage. Paths depend on `fixtures`: real runs use `data/{raw,interim,out}` and
`pipeline/sources.yaml`; fixture runs use `pipeline/fixtures/_run/` and
`pipeline/fixtures/sources.yaml`. Fixture sources reuse the real source ids
(`natural_earth_land`, `ghsl_pop`, `geoboundaries_adm0/1`, `cckp_hd35`, ...) so stages and
`dimensions.yaml` work unchanged in both modes.

**Resolution plan** (`pipeline/resolution_plan.yaml`, fixtures: `pipeline/fixtures/resolution_plan.yaml`,
`resplan.py`, SPEC §9.1, §13.31-34). `land` entries (res 4, 5) cover every land cell; `children`
entries (res 6: US/EU/UK/EFTA or near urban clusters; res 7: urban centres) are H3 children of
matching parents from `urban.parquet` (the `urban` stage, GHS-SMOD) and adm0. Each entry names its
zooms and PMTiles archive (`hexes`, `hexes_nbhd`, `hexes_city`); the tiler and web read them via the manifest.
Derived resolutions are scored against res-5 distributions (`reference.py`); `export` sets `ref`
on refined parents so the web hides them under the finer layer. Raster aggregation takes a cell
set (`h3util.CellSet`) so derived resolutions cost what their cells cost.

**Stage contract.** Each `pipeline/stages/<name>.py` exposes `run(settings)`. Stages write one
parquet per resolution (`hexes_r{res}.parquet` from `grid`; `pop_r{res}`, `admin_r{res}`,
`hazards_r{res}`, `dims_r{res}`, `score_r{res}`) keyed on `h3`, and `sanity.load_merged` joins
whatever exists. Idempotency is via `stage_cache.is_fresh/record` (a `.meta.json` sidecar
fingerprinting inputs + params); `--force` bypasses it, and a code change needs `--force` too.
`--bbox` runs write to `interim/bbox_*/` and `out/bbox_*/`; `Settings.cache_dir` (extracted
archives, prepared layers) is shared. `timing.timed` wraps every stage (`timings.json`).

**Prep layer.** `pipeline/prep/<source>.py` turns one raw source into the joinable table whose
columns `dimensions.yaml` names (`LOADERS` in `prep/__init__.py`, cached as (Geo)Parquet under
`interim/prep/`, `PREP_VERSION` invalidates). Fixture sources pass through unchanged, so fixture
files carry the final column names. A missing real download is skipped with its recipe printed
and the next joiner (e.g. WHR for SHDI) takes over.

**Scores, export, tiles, publish.** `scoring.py` (midrank percentile per domain, min-max within
source, bivariate class); `hazards` scores itself, `score` does composites and life dims;
`export` writes `data/out/hexes_r{res}.parquet` + `manifest.json` (`manifest.py`, §6.3);
`tiles` uses `tiler.py` (pure Python, hex4 z2-4 slim at z2, hex5 z5-7; tippecanoe optional);
`publish` targets `local` (web/public/data) or `r2` (boto3, `.env`) and refuses sources whose
`verified` is not `confirmed` (only sources actually used count).

**Registries.** `pipeline/registry.py` loads `sources.yaml` (one entry per dataset; `access` is
`direct | manual | fixture`; `verified` is `confirmed | search | none`) and `dimensions.yaml`
(everything a person can weight, incl. hazards and wellbeing; `kind` is `score | signed |
composition`; each has ordered `joiners`). `fetch` refuses any source whose `license` or direct
`url` is `VERIFY` (invariant 4). `manual` sources (Aqueduct Floods via Earth Engine, see
`docs/gee-export.md`; GDL SHDI via registration; HUD FMR because huduser.gov's WAF answers
non-browser clients with an empty 202) are checked for presence, not downloaded. A present file
with no CHECKSUMS entry is recorded, not re-downloaded; an empty body is an error.

**Raster to H3.** `pipeline/h3util.aggregate_raster` rasterizes hex ids into each raster window
and groups pixels with `np.bincount` (exact sums/means/fraction-above). h3ronpy was evaluated and
rejected because it samples at cell centres rather than aggregating pixels (§15.11). Rasters
coarser than the hex (0.25° CCKP) use `sample_at_centroids` instead. Rasters must already be
EPSG:4326.

**Joiners** (`pipeline/joiners/`): `polygon_centroid`, `iso_lookup`, `area_weighted_overlay`
(population-weighted via `weight_field`, equal-area CRS 6933, `min_coverage` guard),
`point_density`, and the hex-level pair `raster_mean` (tag `hex`; `decimate` block-averages 100 m
rasters to 1 km first, `sample: centroid` for rasters coarser than the hex) and `point_mean`
(weighted mean of points per hex). All return a Series aligned to the hexes index with NaN for
missing, never 0. The `dims` stage drives them from `dimensions.yaml`; raster sources reach it
through `prep.load_raster` (`RASTER_LOADERS` in `prep/__init__.py` build NetCDF / multi-file
sources into one GeoTIFF under `interim/prep/`). Resolution tags: `hex`, `grid` (Eurostat 1 km
census cells), `basin`, `admin1`, `county`, `tract`, `area` (small areas outside the US, England
LSOA), `national`, `none`; dimension groups: `hazard`, `wellbeing`, `life`, `env`
(present-day environment, never part of `exposure`, SPEC §13.28).

**Fixture world** (`pipeline/fixtures/make_fixtures.py`, VERSION 6): a 4°x4° synthetic region
(countries XKA/XKB with user-assigned ISO2 `XA`/`XB` via `Settings.iso_overrides`, five admin1
regions, four towns, a zero-population desert, a coast, an island), heat/flood/water-stress
inputs, tabular wellbeing, and stand-ins for every life-dimension source (GSAP, OECD TL2,
ILOSTAT, ACS-like tracts, SLD block groups, districts, counties, BEA-like states, ICP / WDI
price levels, HUD-like rents) and rasters / point sets for the hex-level layers (travel time,
PM2.5, 0.002° tree cover, 0.25° burned area, Ookla-like speed points). Regeneration is
content-deterministic; bump `VERSION` when the world changes (a regenerated fixture file is
re-copied by `fetch` even when `_run/` has an older copy). Tests get a temp run dir from
`tests/conftest.py`.

**Web** (`web/`, Next.js 16 static export): `src/lib/` holds pure, vitest-covered logic (URL
state, MapLibre expressions incl. the §20.5 composite, layer stack, palette per theme, inspector
model, `chart.ts` as the TypeScript twin of the match expression, tooltip, summary, compare,
search ranking, sheet snaps, theme and intro flags); components are thin. `page.tsx` reads
`public/data/manifest.json` at build time. MapLibre v6 needs `setWorkerUrl("/maplibre-gl-worker.mjs")`;
`scripts/copy-worker.mjs` copies the worker and its shared chunk into `public/` before dev/build.
The map container needs an explicit size (MapLibre's CSS overrides `position`). Design tokens are
CSS variables in `globals.css` exposed to Tailwind via `@theme inline`; `data-theme` on `<html>`
(set before paint by `THEME_BOOT_SCRIPT`, remembered in localStorage) swaps them, and the map swaps
its OpenFreeMap style with `setStyle(url, { transformStyle })` so the hex source and layers survive
(the hatch image is re-added on `styleimagemissing`). Fonts come from `@fontsource-variable`
packages, so no request leaves the origin. `MapView` registers map handlers once and reads state
and callbacks through refs. Place search reads `public/gazetteer.json` (committed; rebuild with
`uv run python web/scripts/build_gazetteer.py` after `python -m pipeline fetch --only
natural_earth_places`). Below 640px the panels live in a bottom sheet. Playwright screenshots go
under `.playwright-mcp/` (ignored).

## Rules that are easy to break

- Missing data is never 0: hazard/dimension values stay NaN with `_ok = false` / `_res = none`.
  The one documented exception is `population` (a count) in the `pop` stage.
- Keep tile attribute names short (they ship in every vector tile) and follow §6.1 naming:
  `{id}_raw / {id}_score / {id}_res`, `{id}_lean` for signed, `{id}_w/b/h/a/o/maj` for composition.
- Never percentile a US-only value against the world; scoring domains are per joiner (§20.4).
- No paid or non-redistributable data (Walk Score, Cook PVI, NHGIS, IPUMS, GreatSchools, Numbeo,
  SEDA without permission). SHDI is non-commercial only and the project is non-commercial (§13.13).
- `data/raw/`, `data/interim/`, `data/out/`, `pipeline/fixtures/{data,_run}/`, `web/public/data/`
  and `.env` are gitignored; only `data/raw/CHECKSUMS` is committed. GitHub Actions runs lint,
  tests, the fixture pipeline and the web build only; never data pulls.
- Bash on this laptop truncates commands beyond ~8k characters and `pytest | tail` hides pytest's
  exit code: write long files with the Write tool and check pytest's status before committing.
- Never hand-write this file from scratch; regenerate with `/init` and edit, and update it at the
  end of every session along with the §17 checkboxes in `SPEC.md`.
