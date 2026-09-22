# livability-map

A free, global, explorable map that puts **projected climate hazard exposure** (heat, riverine
flood, coastal flood, water stress; one moderate scenario, 2050) beside **present-day wellbeing**
and a set of **life dimensions** you can weight yourself (jobs, transit, schools, LGBTQ+
protection and presence, political lean, racial composition, income mix, housing cost,
healthcare), on H3 hexagons at tens-of-km resolution, built only from open-licensed data.

It does **not** recommend where to live. It shows evidence, shows its sources, and shows its
gaps. Every number on the map is traceable to a dataset, a vintage and a license. Missing data
renders as missing, never as zero.

Status: Sessions 1-7 built (2026-09-22). The pipeline runs end to end on real data at H3 res 4
(res 5 pending) and the map app runs locally; publishing to Cloudflare R2 / Pages waits on
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
  |  dims      prep/<source>.py turns each raw source into a joinable layer; for each dimension in       |
  |            dimensions.yaml run its joiners (§20.3): polygon_centroid | iso_lookup |                   |
  |            area_weighted_overlay | point_density -> {id}_raw, {id}_res (admin1|county|tract|national|none)|
  |  score     exposure = mean(available hazard scores), coverage = count(*_ok)                           |
  |            {id}_score = percentile within the dimension's coverage domain (§8.2, §20.4)               |
  |            wb_score, bivar class 1-9 (§8.4)                                                            |
  |  export    data/out/hexes_r{res}.parquet + manifest.json (§6.3); --geojson for tippecanoe             |
  |  tiles     python tiler (tippecanoe optional) -> hexes.pmtiles: hex4 z2-4, hex5 z5-7 (§9, §13.18)    |
  |  publish   hexes.pmtiles + manifest.json -> R2 via boto3 (.env) or web/public/data (local) (§13.24)   |
  +-----------------------------------------------+--------------------------------------------------------+
                                                  |  static files only
                                                  v
  +----------------------------------------+    range      +------------------------------------------+
  |  web/  Next.js 16 static export        | <--requests-- |  Cloudflare R2 (public, custom domain)   |
  |  on Cloudflare Pages                   |               |  hexes.pmtiles   manifest.json           |
  |  MapLibre GL JS v6 + pmtiles protocol  |               |  (basemap: OpenFreeMap)                  |
  |  views: bivariate | per hazard |       |               +------------------------------------------+
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
uv venv && uv pip install -e ".[dev]"      # or: uv sync
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
  stages/               fetch grid pop admin hazards dims score export tiles publish
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
