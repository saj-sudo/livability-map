// Our own basemap style on OpenFreeMap's tiles and glyphs (SPEC §9.4, §13.50): a quiet atlas
// ground. Land in the paper tone, a slightly different sea, country and region borders as
// hairlines, a handful of labels, no roads and no buildings. The stock dark style drew roads and
// borders over the hexes; here the hex stack goes above every line (it is inserted before
// COUNTRY_TOP_ID, see lib/style.ts) and below the labels. COUNTRY_TOP_ID repeats the country
// borders above the hexes and is shown only in the bivariate view, where a country whose
// wellbeing is one national figure must read as a country, not as a colour (§9.3).

import type { LayerSpecification, StyleSpecification } from "maplibre-gl";
import { BASEMAP_GLYPHS, BASEMAP_TILEJSON } from "./config";
import { GROUND } from "./ground";
import type { Theme } from "./theme";

export const BASEMAP_SOURCE = "openmaptiles";
export const COUNTRY_TOP_ID = "country-top";
export const BASEMAP_ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">© OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';

// English name where the tile has one (the page is in English), else Latin script, else local
const NAME = ["coalesce", ["get", "name:en"], ["get", "name:latin"], ["get", "name"]];
const COUNTRY_LINE = ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]];

export function basemapStyle(theme: Theme): StyleSpecification {
  const g = GROUND[theme];
  const src = { source: BASEMAP_SOURCE };
  const text = (size: unknown, font: string) => ({ "text-field": NAME, "text-font": [font], "text-size": size, "text-max-width": 8 });
  const ink = (color: string) => ({ "text-color": color, "text-halo-color": g.halo, "text-halo-width": 1.2 });
  const layers = [
    { id: "background", type: "background", paint: { "background-color": g.land } },
    { id: "water", type: "fill", ...src, "source-layer": "water", filter: ["!=", ["get", "brunnel"], "tunnel"], paint: { "fill-color": g.sea } },
    { id: "region-line", type: "line", ...src, "source-layer": "boundary", minzoom: 4, filter: ["all", ["==", ["get", "admin_level"], 4], ["!=", ["get", "maritime"], 1]], paint: { "line-color": g.line, "line-width": 0.6, "line-dasharray": [2, 2] } },
    { id: "country-line", type: "line", ...src, "source-layer": "boundary", filter: COUNTRY_LINE, paint: { "line-color": g.line, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.6, 8, 1.4] } },
    // --- the hex layers are inserted here ---
    { id: COUNTRY_TOP_ID, type: "line", ...src, "source-layer": "boundary", filter: COUNTRY_LINE, layout: { visibility: "none" }, paint: { "line-color": g.label, "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.8, 8, 1.8], "line-dasharray": [3, 2], "line-opacity": 0.8 } },
    { id: "sea-label", type: "symbol", ...src, "source-layer": "water_name", filter: ["==", ["geometry-type"], "Point"], layout: { ...text(["interpolate", ["linear"], ["zoom"], 2, 11, 7, 14], "Noto Sans Italic"), "text-letter-spacing": 0.08 }, paint: { "text-color": g.seaLabel, "text-halo-color": g.halo, "text-halo-width": 0.6 } },
    { id: "city-label", type: "symbol", ...src, "source-layer": "place", minzoom: 4, filter: ["all", ["==", ["get", "class"], "city"], ["<=", ["coalesce", ["get", "rank"], 99], ["step", ["zoom"], 3, 5, 5, 6, 8, 8, 99]]], layout: { ...text(["interpolate", ["linear"], ["zoom"], 4, 11, 10, 14], "Noto Sans Regular"), "text-padding": 6 }, paint: ink(g.label) },
    { id: "town-label", type: "symbol", ...src, "source-layer": "place", minzoom: 9, filter: ["==", ["get", "class"], "town"], layout: { ...text(12, "Noto Sans Regular"), "text-padding": 6 }, paint: ink(g.label) },
    { id: "country-label", type: "symbol", ...src, "source-layer": "place", maxzoom: 7, filter: ["all", ["==", ["get", "class"], "country"], ["<=", ["coalesce", ["get", "rank"], 99], ["step", ["zoom"], 1, 3, 2, 4, 3, 5, 4, 6, 5]]], layout: { ...text(["interpolate", ["linear"], ["zoom"], 2, 11, 6, 15], "Noto Sans Bold"), "text-padding": 8 }, paint: ink(g.label) },
  ];
  return {
    version: 8,
    name: `atlas ground (${theme})`,
    glyphs: BASEMAP_GLYPHS,
    sources: { [BASEMAP_SOURCE]: { type: "vector", url: BASEMAP_TILEJSON, attribution: BASEMAP_ATTRIBUTION } },
    layers: layers as unknown as LayerSpecification[],
  };
}
