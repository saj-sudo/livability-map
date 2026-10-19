# livability-map

A free, global, explorable map that puts **projected climate hazard exposure** (heat, riverine
flood, coastal flood, water stress; one moderate scenario, 2050) beside **present-day wellbeing**
and a set of **life dimensions** you can weight yourself (jobs, transit, schools, LGBTQ+
protection and presence, political lean, income mix, housing cost burden, healthcare, cost of
living, rent, travel time to healthcare, internet speed; racial composition is shown per place
as context, never weighted) plus the
**present-day environment** (air quality, tree cover, wildfire, drought risk), on H3 hexagons at
tens-of-km resolution, built only from open-licensed data.

It does **not** recommend where to live. It shows evidence, shows its sources, and shows its
gaps. Every number on the map is traceable to a dataset, a vintage and a license. Missing data
renders as missing, never as zero.

Status: Sessions 1-9 built (2026-09-22). The pipeline runs end to end on real data at H3 res 4
and res 5 (18 dimensions, 146 MB of tiles) and the map app runs locally; publishing to Cloudflare R2 / Pages waits on
credentials in `.env`, and two registration-gated inputs (Global Data Lab SHDI, MIT Election Lab
county returns) on a manual download. See [`SPEC.md`](SPEC.md) for the full spec; section
numbers below refer to it.

## Why this and not something that exists

Global future-climate maps (Probable Futures, Climate Impact Explorer, Aqueduct) carry no
wellbeing and no weighting. Weighted "where should I live" tools (Movemap, Dwellics, WhereNext)
use present-day climate only. US climate-plus-social tools (FEMA NRI, Climate Vulnerability
Index) are framed as "who needs help", not "where would I live", and are politically fragile.
The only global hybrid, AlphaGeo, is proprietary and enterprise-priced. Details in SPEC §18.

## Architecture (SPEC §5)

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

## Quickstart (pipeline, fixture world)

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked --extra dev               # exact versions from uv.lock
uv run python -m pipeline --help
uv run python -m pipeline --fixtures all   # synthetic 4x4 degree world, runs in seconds
uv run pytest
uv run ruff check .
```

`--fixtures` generates a deterministic synthetic region under `pipeline/fixtures/data/` (two
countries, five admin1 regions, four towns, a desert, a coast, an island) and runs every
implemented stage against it, printing the SPEC §8.5 counts and spot checks. Real data never
enters the repo.

## Web app

```bash
uv run python -m pipeline --fixtures --res 4 all   # publishes fixture tiles to web/public/data/
cd web && npm install && npm run dev               # http://localhost:3000
npm test && npm run lint && npm run build           # vitest, eslint, static export to web/out/
npm run deploy                                     # Cloudflare Pages via wrangler (needs .env, see docs/deploy.md)
```

## Running on real data (laptop)

1. Confirm each source in `pipeline/sources.yaml` first-hand and log it in SPEC §15. The
   `fetch` stage refuses any source whose license or URL is still `VERIFY`.
2. Two sources are `access: manual`: Aqueduct Floods (one-time Google Earth Engine export, see
   [`docs/gee-export.md`](docs/gee-export.md)) and Global Data Lab SHDI (free registration).
3. `python -m pipeline fetch` then `python -m pipeline --res 4 all` for a first global pass
   (about 35 minutes and 6 GB of RAM on a laptop); use `--bbox minlng,minlat,maxlng,maxlat` to
   iterate on a region (Dhaka, Phoenix, Reykjavik, the Sahel are the spot checks; bbox runs get
   their own `data/interim/bbox_*/` directories).
4. Global 1 km rasters are tens of GB and need laptop RAM; GitHub Actions only runs lint and
   tests on fixtures.

## Repo layout

```
SPEC.md                 the spec; build prompts cite its section numbers
pipeline/               Python pipeline package (python -m pipeline <stage>)
  sources.yaml          every dataset: url, format, license, vintage, attribution (§6.2)
  dimensions.yaml       everything a person can weight, with joiners (§20.2)
  stages/               fetch urban grid pop admin hazards dims score export tiles validate publish
  prep/                 one loader per real source -> the columns dimensions.yaml names
  joiners/              polygon_centroid iso_lookup area_weighted_overlay point_density (§20.3)
  crosswalks/           manual OECD TL2 -> geoBoundaries ADM1 overrides (§13.21)
  h3util.py             polygon -> cells, raster -> H3 aggregation (rasterize + bincount)
  scoring.py            percentile / min-max / bivariate class (§8)
  tiler.py              pure-Python PMTiles builder (§13.18)
  manifest.py           manifest.json (§6.3)
  fixtures/             synthetic world generator and fixture sources.yaml (§11.1)
tests/                  pytest, runs on fixtures only
docs/                   recipes (Earth Engine export)
web/                    Next.js 16 static export: MapLibre map, inspector, priorities, /methodology, /about
data/                   gitignored raw / interim / out; data/raw/CHECKSUMS is committed
```

## Licensing posture

Non-commercial for the foreseeable future (SPEC §13.13). All sources are CC BY 4.0, public
domain, ODC-BY or CC0, except Global Data Lab SHDI (free with citation, non-commercial only),
which the manifest and `/methodology` state plainly. Sources with non-redistributable terms
(Walk Score, Cook PVI, NHGIS, IPUMS, GreatSchools, Numbeo, SEDA without permission) are excluded.

Code: MIT.
