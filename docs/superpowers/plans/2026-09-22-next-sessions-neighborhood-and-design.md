# Next sessions (outline agreed 2026-09-22; each starts with brainstorming + a plan)

## Session 8: neighborhood resolution

Goal: hexes at neighborhood scale where people choose between neighborhoods, without a global
res-7 archive (~28 M land cells).

- Variable resolution: H3 res 7 (~5 km²) inside urban footprints (GHSL urban centres / SMOD
  classes or a population-density threshold from the existing `pop` stage), res 6 (~36 km²)
  across the US and Europe (and other countries with grid statistics), res 5 elsewhere. A new
  `urban` stage writes the mask; `grid` takes a resolution plan instead of a flat list.
- Tiles: layers hex4 z2-4, hex5 z5-7, hex6 z8-9, hex7 z10-13 (only where built); the tiler and
  the web layer stack already take layer lists from the manifest.
- Layers that are already neighborhood-scale: the four hazards (1 km), population, and the
  extras (travel time to healthcare 1 km, PM2.5 1 km, tree cover 100 m, Ookla ~600 m tiles).
- Socioeconomic detail by country, one prep loader + scoring domain each, densest markets first:
  US ACS tracts (wired), Eurostat 1 km census grid 2021 (CC BY; population by age/employment,
  place of birth), UK LSOA Index of Multiple Deprivation (OGL), German Zensus 2022 100 m grid,
  Dutch CBS 100 m grid, French IRIS, Canadian dissemination areas, Australian SA2.
- SPEC changes: new resolution tags `hex` (hex-computed) and `grid` (statistical grid), §9.1
  zoom plan, §6.1 attributes per layer, §11 sizing.

## Session 9: visual design and search

Goal: make the map engaging (SPEC §13.10 "new visual identity"); run with the frontend-design
skill.

- Identity: type, colour, spacing; dark basemap option (OpenFreeMap `dark`), a redesigned
  bivariate palette with a proper 3x3 legend, subtle hex outlines instead of the flat grey.
- Place search with a bundled gazetteer (geoBoundaries admin1 + Natural Earth populated places
  or GHSL urban centres) so nothing calls a third party (invariant 7).
- Hover tooltip with a mini readout; inspector with a priorities radar/bar chart and a
  plain-language summary line; "compare two places" (SPEC v2); short guided intro.
- Mobile layout (panel as a bottom sheet).

## Session 10: point readouts (property-level evidence, no property-level hexes)

Goal: click a house and read the physical layers under that point, with sources, without any
per-property score. Decided 2026-09-22 (SPEC §3, §16).

- Data (verify first-hand before coding, SPEC §15): FEMA National Flood Hazard Layer (US, public
  domain, vector zones + base flood elevations); UK Environment Agency flood zones (OGL);
  Copernicus DEM GLO-30 (free) with a sea-level bathtub for coastal inundation (CoastalDEM 90 m
  is non-commercial, fine here); Landsat 8/9 land-surface temperature composites for urban heat
  (public domain); ESA WorldCover 10 m or Meta canopy height 1 m (CC BY 4.0) for trees; EU
  Environmental Noise Directive strategic maps and the US BTS National Transportation Noise Map
  30 m (public domain); SILVIS wildland-urban interface (US); FCC broadband availability
  (US, address level, public).
- Pipeline: a `cogs` stage that clips each layer to the regions built (US + EU first), writes
  cloud-optimized GeoTIFFs with overviews, records size and checksum in the manifest under
  `assets`, and publishes them to R2 next to the tiles. Vector layers (FEMA zones) rasterize to
  the layer's native resolution first, or ship as a separate PMTiles vector archive.
- Web: `lib/point.ts` reads the pixel under a click from each COG with geotiff.js range
  requests (no server, invariant 5), a "What is here" panel lists value, unit, source, vintage
  and a caveat per layer, and a "no coverage here" state for regions without assets. Address
  search stays the bundled gazetteer; street addresses need OpenAddresses or Overture per
  region and are a later decision.
- Storage: roughly 100 GB per global 10 m layer, so regions are chosen per layer and listed in
  the manifest; R2 at these sizes costs a few dollars a month.
- SPEC: §3 wording already changed; add §6.4 (assets in the manifest), §9.5 (point reads), §10
  ("What is here" panel), §11 (asset sizes).

## Session 11: block hexes (res 9/10 inside urban centres)

Goal: block-level hexes where the physical layers and distances genuinely vary block to block,
one region at a time.

- Reuse the Session 8 `urban` mask and resolution plan; add res 9 (~0.1 km²) or 10 (~15,000 m²)
  inside urban centres. About 15 M (res 9) or 100 M (res 10) cells across all urban centres, so
  each region is its own PMTiles archive with a size cap in SPEC §11, and the web app loads the
  archive for the region in view.
- Layers: the Session 10 rasters aggregated per block hex (`raster_mean`), plus distances:
  walking time to transit stops (GTFS from the Mobility Database), parks, groceries and clinics
  (OSM, ODbL: the derived table becomes share-alike, a licence decision like Ookla's), computed
  with a self-hosted router (Valhalla or OSRM) per region. Socioeconomic layers stay at block
  group / output area and are shown as context, never per block below that.
- Compute: whole countries at res 10 need a build machine bigger than the laptop (routing
  graphs are tens of GB; aggregation is hours per country). A few metros first.
- SPEC: tags `block` and `street` in §6.1, zoom plan z14-16 in §9.1, §11 sizing, §17 criteria.

