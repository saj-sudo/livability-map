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
