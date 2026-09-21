# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A global climate-livability map: projected climate hazard exposure (4 hazards, one scenario, 2050)
beside present-day wellbeing and user-weighted "life dimensions" on H3 hexes, built only from
open-licensed data. `SPEC.md` is the source of truth; build prompts and code comments cite its
section numbers (§5 architecture, §6 data model, §8 scoring, §13 decisions, §15 verification log,
§16 session plan, §20 life dimensions). Read it before changing anything structural, and update the
§5 ASCII diagram (mirrored in `README.md`) in the same change when the pipeline shape changes.

Two-language repo: `pipeline/` (Python 3.11+, Sessions 1-5) and `web/` (TypeScript, Sessions 6-7,
not started). Status: Session 1 done (fetch, grid, pop, admin, joiners, fixtures, tests).

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
```

CLI options (`--fixtures`, `--res`, `--bbox minlng,minlat,maxlng,maxlat`, `--force`) are typer
callback options and must precede the stage name. `all` runs stages in order and stops cleanly
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

**Stage contract.** Each `pipeline/stages/<name>.py` exposes `run(settings)`. Stages write one
parquet per resolution (`hexes_r{res}.parquet` from `grid`; `pop_r{res}`, `admin_r{res}`, ...)
keyed on `h3`, and `sanity.load_merged` joins whatever exists. Idempotency is via
`stage_cache.is_fresh/record` (a `.meta.json` sidecar fingerprinting inputs + params); `--force`
bypasses it. Planned stages raise `NotImplementedStage` with the target session.

**Registries.** `pipeline/registry.py` loads `sources.yaml` (one entry per dataset; `access` is
`direct | manual | fixture`; `verified` is `confirmed | search | none`) and `dimensions.yaml`
(everything a person can weight, incl. hazards and wellbeing; `kind` is `score | signed |
composition`; each has ordered `joiners`). `fetch` refuses any source whose `license` or direct
`url` is `VERIFY` (invariant 4). `manual` sources (Aqueduct Floods via Earth Engine, see
`docs/gee-export.md`; GDL SHDI via registration) are checked for presence, not downloaded.

**Raster to H3.** `pipeline/h3util.aggregate_raster` rasterizes hex ids into each raster window
and groups pixels with `np.bincount` (exact sums/means/fraction-above). h3ronpy was evaluated and
rejected because it samples at cell centres rather than aggregating pixels (§15.11). Rasters
coarser than the hex (0.25° CCKP) use `sample_at_centroids` instead. Rasters must already be
EPSG:4326.

**Joiners** (`pipeline/joiners/`): `polygon_centroid`, `iso_lookup`, `area_weighted_overlay`
(population-weighted via `weight_field`, equal-area CRS 6933, `min_coverage` guard),
`point_density`. All return a Series aligned to the hexes index with NaN for missing, never 0.
`admin` already uses `polygon_centroid`; the `dims` stage (Session 4) will drive them from
`dimensions.yaml`.

**Fixture world** (`pipeline/fixtures/make_fixtures.py`): a 4°x4° synthetic region (countries
XKA/XKB with user-assigned ISO2 `XA`/`XB` via `Settings.iso_overrides`, five admin1 regions, four
towns, a zero-population desert, a coast, an island), plus heat/flood/water-stress inputs and
tabular wellbeing and US-like tract/county/transit layers. Regeneration is content-deterministic;
bump `VERSION` when the world changes. Tests get a temp run dir from `tests/conftest.py`.

## Rules that are easy to break

- Missing data is never 0: hazard/dimension values stay NaN with `_ok = false` / `_res = none`.
  The one documented exception is `population` (a count) in the `pop` stage.
- Keep tile attribute names short (they ship in every vector tile) and follow §6.1 naming:
  `{id}_raw / {id}_score / {id}_res`, `{id}_lean` for signed, `{id}_w/b/h/a/o/maj` for composition.
- Never percentile a US-only value against the world; scoring domains are per joiner (§20.4).
- No paid or non-redistributable data (Walk Score, Cook PVI, NHGIS, IPUMS, GreatSchools, Numbeo,
  SEDA without permission). SHDI is non-commercial only and the project is non-commercial (§13.13).
- `data/raw/`, `data/interim/`, `data/out/`, and `pipeline/fixtures/{data,_run}/` are gitignored;
  only `data/raw/CHECKSUMS` is committed. GitHub Actions runs lint, tests and the fixture pipeline
  only; never data pulls.
- Never hand-write this file from scratch; regenerate with `/init` and edit, and update it at the
  end of every session along with the §17 checkboxes in `SPEC.md`.
