# livability-map

A free, global, explorable map that puts **projected climate hazard exposure** (heat, riverine
flood, coastal flood, water stress; one moderate scenario, 2050) beside **present-day wellbeing**
and a set of **life dimensions** you can weight yourself (jobs, transit, schools, LGBTQ+
presence, political lean, racial composition, income mix, housing cost burden, healthcare, cost
of living, rent, travel time to healthcare and to a city, walking time to healthcare, internet
speed, relative wealth, armed conflict nearby, working water points) plus the **present-day
environment** (air quality, tree cover, wildfire, drought risk), on H3 hexagons from about
1,770 km² on all land down to about 5 km² inside urban centres, built only from open-licensed
data.

LGBTQ+ presence is a proxy and US-only: same-sex couple households per 1,000 households from the
Census ACS, by tract. LGBTQ+ protection (state and national policy) is not on the map yet; the
usable sources are waiting on permission from their publishers (SPEC §20.6).

It does **not** recommend where to live. It shows evidence, shows its sources, and shows its
gaps. Every number on the map is traceable to a dataset, a vintage and a license. Missing data
renders as missing, never as zero.

**Status (2026-09-24):** the pipeline runs end to end on real data on a laptop, and the map app
runs locally against its output. The map is not deployed yet: publishing to Cloudflare R2 /
Pages needs credentials in `.env` (see [`docs/manual-steps.md`](docs/manual-steps.md)).

The current build has H3 res 4 and 5 on all land, res 6 across the US, EU, UK, EFTA and urban
clusters, and res 7 inside urban centres, with 27 dimensions (4 hazards, wellbeing, 18 life
dimensions, 4 environment layers) in three tile archives (`hexes` 191 MB, `hexes_nbhd` 264 MB,
`hexes_city` 152 MB). Three inputs wait on a manual download, and until they arrive these layers
are empty or coarser than designed:

- **Political lean** (MIT Election Lab county returns): empty. It has no other source.
- **Rent in the US** (HUD Fair Market Rents): empty in the US. Germany, the Netherlands and
  Australia are populated from their national statistics offices.
- **Regional wellbeing** (Global Data Lab Subnational HDI): wellbeing falls back to the national
  World Happiness Report value wherever that report has one.

See [`SPEC.md`](SPEC.md) for the full spec; section numbers below refer to it.

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
  |  publish   every archive + manifest.json -> R2 via boto3 (.env) or web/public/data (local) (§13.24)   |
  +-----------------------------------------------+--------------------------------------------------------+
                                                  |  static files only
                                                  v
  +----------------------------------------+    range      +------------------------------------------+
  |  web/  Next.js 16 static export        | <--requests-- |  Cloudflare R2 (public, custom domain)   |
  |  on Cloudflare Pages                   |               |  hexes / hexes_nbhd / hexes_city .pmtiles|
  |  MapLibre GL JS v6 + pmtiles protocol  |               |  manifest.json                           |
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
2. Some sources need a person: Aqueduct Floods (one-time Google Earth Engine export, see
   [`docs/gee-export.md`](docs/gee-export.md)), and the registration, browser-check and
   permission items in [`docs/manual-steps.md`](docs/manual-steps.md) (Global Data Lab SHDI, HUD
   Fair Market Rents, MIT Election Lab county returns, among others).
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

Non-commercial for the foreseeable future (SPEC §13.13). Most sources are CC BY 4.0, public
domain, ODC-BY, CC0 or an open reuse licence from a public publisher (UK OGL, Etalab, Statistics
Canada, dl-de/by, Eurostat, OECD). The exceptions, which the manifest and `/methodology` state plainly:

- Global Data Lab SHDI: free with citation, non-commercial only.
- Ookla open data (internet speed): CC BY-NC-SA 4.0, so the derived `net_*` attributes are
  redistributed under the same licence.
- Meta Data for Good Relative Wealth Index (relative wealth): CC BY-NC 4.0.
- WPdx+ water points: recorded as CC BY-SA 4.0 and labelled share-alike, pending the publisher's
  confirmation (see [`docs/manual-steps.md`](docs/manual-steps.md)).

Sources with non-redistributable terms (Walk Score, Cook PVI, NHGIS, IPUMS, GreatSchools, Numbeo,
SEDA without permission) are excluded.

Code: MIT, see [`LICENSE`](LICENSE). The MIT licence covers the code in this repository only;
data derived from the sources keeps each source's terms, listed per source in
`pipeline/sources.yaml`.
