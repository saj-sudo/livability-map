# Source candidates from the "Data/Sources Repo" list (2026-11-04)

## Context

Saj asked (2026-11-04) for a thorough pass over the public Notion list (https://pinto-pot-721.notion.site/Data-Sources-Repo-...)
to judge which sources would be useful or interesting for the climate-livability map, and what useful
overlaps they create with what's already there. I read the whole page (all ~1,070 lines, 21 sections) and
checked every candidate against `pipeline/dimensions.yaml`, `pipeline/sources.yaml` and SPEC §13/§20.

Honest headline: the list is an investigative-journalism toolkit, not a geodata catalogue. Roughly 85%
of it is out of scope (arms trade, offshore leaks, sanctions, terrorism, sports, food waste, corporate
registries, aggregator sites). Of the rest, most items are **national** tables, which SPEC §20.6's design
rule says we don't substitute for a hex-level answer. That leaves about a dozen sources that are genuinely
useful at hex / small-area scale, and five or six that are interesting but need care.

Caveat: licences below are from memory or the page's description, not first-hand. The container blocks
data hosts, so each one is `verified: search` until checked on Saj's laptop (CLAUDE.md, §15).

## Tier 1: worth adding (fills a real gap, sub-national, likely open)

| Source (where in the Notion list) | What it adds | Res / joiner | Licence (unverified) | Overlap it creates |
|---|---|---|---|---|
| **Overture Maps places + transportation** (Mapping & GIS) | Global amenity access: grocery, pharmacy, school, park, transit stop counts within walking distance. Closes the global `transit` gap (SPEC v2 already plans OSM transit) and gives a "15-minute" dimension | hex, `point_radius` | places CDLA-Permissive 2.0; transportation ODbL (keep that layer ODbL, §20.6 note) | Pairs with MAP `walkcare`/`care` (2019-2020 rasters): Overture refreshes facility locations; `city` stays the macro access proxy |
| **FEMA National Risk Index** (US: FEMA data feeds) | US present-day hazards we don't model: hurricane, tornado, earthquake, landslide, hail; plus Social Vulnerability and Community Resilience | tract, `area_weighted_overlay` | public domain | Exposure (our 2050 hazards) x vulnerability (NRI SoVI): "who is exposed" vs "what is exposed". Earthquake also fits the planned "GEM seismic as labelled non-climate" |
| **CDC PLACES** (US: BRFSS / chronicdata.cdc.gov) | Tract health outcomes: frequent mental distress, no health insurance, obesity, diabetes | tract | public domain | `health` in the US is supply only (HRSA physicians/10k). PLACES adds outcomes, so supply vs need becomes visible |
| **Opportunity Atlas** (Other govt sources) | Kids' adult income by tract, by parental income | tract | Opportunity Insights terms, check | Strongest single upgrade to the "Raising kids" preset; complements `school` (district grad rates) and `incmix` |
| **Eurostat Perception of Quality of Life in European Cities** (Borders > Europe) | City-level survey (83 cities): "good place for gay/lesbian people", "good place for immigrants", feeling safe, satisfaction with green space | city polygon, `polygon_centroid` (needs city boundaries, e.g. Eurostat LAU/FUA) | EC reuse, CC BY 4.0 | First non-US `lgbtq` signal that's sub-national, so it respects the §20.6 rule. Also seeds a "welcoming to immigrants" dimension |
| **Climate TRACE assets + Global Energy Monitor trackers** (Climate/Env, methane) | Point locations of power plants, refineries, steel, cement, landfills, coal mines | hex, `point_radius` (count or emissions within 5-10 km) | Climate TRACE CC BY 4.0; GEM CC BY 4.0 | ACAG PM2.5 is regional; facility proximity is the local hotspot. With `wealth`/`race`/`incmix` it enables an environmental-justice lens |
| **Copernicus CAMS / Sentinel-5P NO2** (Copernicus, NASA Earthdata) | NO2, a traffic and combustion proxy | hex, `raster_mean` | CC BY 4.0 (CAMS); NASA open | `air` is PM2.5 only. NO2 tracks roads and traffic at a much finer gradient inside cities |
| **USDA SNAP retailer locations + Food Environment / Food Access Atlas** (US) | Grocery access | points `point_radius`; tract / county | public domain | US-scale check on the Overture grocery counts; links to `incmix` (food deserts) |

## Tier 2: interesting, add with care

| Source | Why it's interesting | The catch |
|---|---|---|
| **CDC WONDER county homicide rate** (US) | A cleaner US "interpersonal violence" layer than FBI UCR | Suppression below 10 deaths blanks many rural counties. Use multi-year pooling |
| **UNODC homicide / Small Arms Survey GVD** (Crime; Arms) | Global safety beside UCDP `conflict` (UCDP only counts organised violence) | National only, so it breaks the §20.6 rule unless shown as context in the inspector rather than as a scored dim. GVD includes conflict deaths: take the homicide component only, or it double-counts UCDP |
| **IDMC disaster displacement** (Borders; HDX) | Observed displacement as a reality check on projected hazards | National/event-level, so it's useful for methodology and validation, not as a hex layer |
| **EIA state electricity prices / Eurostat household electricity prices** (US EIA; Eurostat) | Heat days x electricity price = a "cost of keeping cool" overlap | State/national. Works as a derived inspector readout, not a weighted dim |
| **EEA (noise, Urban Atlas, Natura 2000)** (Climate/Env) | Noise and green space for the EU | Noise is already planned for Session 10 point readouts. Natura 2000 is a decent EU "nature access" layer |
| **NASA Earthdata / SEDAC GRDI and DHS modelled surfaces** (Climate/Env; Health) | Gridded deprivation and DHS 5 km surfaces fill `wealth` where Meta RWI has no coverage (RWI is 93 LMICs) | Already planned: `docs/manual-steps.md` items 6 (GRDI) and 10 (DHS). Different constructs from RWI, so label them as such |
| **IHME US county life expectancy / healthinequality.org** (Health; Other) | Outcome-side health, by income | IHME terms are non-commercial (OK, §13.13); check redistribution |
| **U.S. Religion Census (ARDA)** (Polls/Surveys) | County congregations: some users (e.g. the queer preset) care about religious climate | Licence for redistribution is unclear; contentious construct |
| **Mapping Police Violence** (Policing) | County-level police killings per capita; relevant to the race and queer presets | Small counts make county rates jumpy; needs 10-year pooling and careful framing |

## Skip, and why (pushback)

- **FBI hate crime and UCR agency data.** Hate-crime reporting is voluntary and patchy: many agencies
  report zero. Places that report less often protect less, so the layer would invert the signal.
  It would mislead, not inform.
- **Missing Migrants, Global Detention Project, IDP/refugee sites, Aegean boat data.** These record human
  harm rather than livability, and mapping the sites of vulnerable populations is a real risk.
  They don't belong in a "where to live" score.
- **GTD / RAND terrorism.** Redistribution is restricted, updates stopped around 2020-21, and the data
  largely overlaps UCDP. **ACLED** is already excluded (§20.6).
- **WVS, Pew, Eurobarometer, GSS, ITUC, WID/WIID, WHO GHO, UNDP, OWID, Gapminder, FAOSTAT.** All
  national. Use them for the inspector's "country context" at most. GDL SHDI already covers the
  sub-national version.
- **OPHI MPI** was already evaluated and rejected (§13.36). **Zillow** is already excluded.
- **GBIF / IUCN.** Sampling bias makes occurrence density a map of where ecologists go.
- **City open-data portals (NYC, SF, London, TfL).** Not uniform. Revisit only for Session 10 point readouts.
- **Everything else** (arms, sanctions, offshore leaks, corporates, media, sports, food waste,
  Kaggle/Statista/aggregators): out of scope or not primary sources.

## Overlaps worth designing for (cross-layer views, not just more layers)

1. **Exposure x vulnerability:** our 2050 hazards x FEMA NRI social vulnerability (US), and x RWI/GRDI (global).
2. **Environmental justice lens:** PM2.5 + NO2 + facility proximity, read against `wealth`, `incmix`, `race`.
   This can be a preset in `web/src/presets.ts`; no new pipeline concept is needed.
3. **Heat that hurts:** `heat` x `trees` x `walkcare`/`care` (plus electricity price as a readout) for the Retiring preset.
4. **Safety split:** UCDP organised violence (have it) vs interpersonal homicide (CDC WONDER US;
   national context elsewhere), shown separately and never summed.
5. **Kids' outcomes:** Opportunity Atlas + `school` + `incmix` for Raising kids.
6. **Health supply vs need:** HRSA physicians + PLACES outcomes + MAP travel time.
7. **Queer community outside the US:** EU cities survey (lgbtq) + Eurostat grid; still greyed out elsewhere.

**Update 2026-11-14:** FEMA NRI and CDC PLACES are wired (SPEC §13.38); Climate TRACE is wired as
the `industry` env layer, a count of large facilities within 10 km (SPEC §13.46), with GEM plants
merged in (§13.49). NO2 (`no2`) and Overture everyday amenities (`amen`) are wired too (§13.49).

## Recommended order, if we build any of it

1. FEMA NRI + CDC PLACES (US, public domain, tract, uses the existing `area_weighted_overlay`: lowest effort)
2. Climate TRACE / GEM facility proximity (global, existing `point_radius`)
3. Eurostat QoL-in-cities lgbtq + immigrant items (needs city polygons)
4. Overture amenities / transit (biggest win, biggest lift: DuckDB bbox reads of planet parquet)
5. NO2, Opportunity Atlas, SNAP after that

Each one follows the existing pattern: a `sources.yaml` entry (`verified: search`), a
`pipeline/prep/<source>.py` loader registered in `prep/__init__.py`, a `dimensions.yaml`
joiner, a fixture stand-in in `make_fixtures.py` (bump VERSION), a SPEC §15 row and §20.6 row.
