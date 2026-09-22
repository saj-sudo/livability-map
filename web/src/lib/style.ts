// The hex layer stack (SPEC §9.3): one vector source with one layer per tile layer in the
// manifest (hex4 z2-4, hex5 z5+ when built), each with a fill per view, a hatch overlay for
// reduced confidence, a dashed outline for national wellbeing fallback, a hover outline and a
// haloed selection outline driven by feature-state. Colours come from the theme's palette.

import type { FilterSpecification, LayerSpecification, Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import type { DimInfo } from "./dims";
import { bivarColor, hatchFilter, inhabitedFilter, nationalFilter, priorityColor, rampFor, scoreColor, type Expr, type Picks, type Weights } from "./expressions";
import { paletteFor, type Palette } from "./palette";
import type { Theme } from "./theme";
import type { ViewId } from "./url";

export const SOURCE_ID = "hexes";
export const HATCH_IMAGE = "hatch";
export const LAYER_KINDS = ["fill", "hatch", "national", "hover", "halo", "selected"] as const;
export type LayerKind = (typeof LAYER_KINDS)[number];

/** A source layer in the archive with the zoom range the tiler built it for (manifest.tiles). */
export interface TileLayer {
  name: string;
  minzoom: number;
  maxzoom: number;
}
export const DEFAULT_TILE_LAYERS: TileLayer[] = [
  { name: "hex4", minzoom: 2, maxzoom: 4 },
  { name: "hex5", minzoom: 5, maxzoom: 7 },
];

export interface ViewOptions {
  view: ViewId;
  dims: DimInfo[];
  weights: Weights;
  picks: Picks;
  theme?: Theme;
}

export const layerId = (kind: LayerKind, layer: string) => `${kind}-${layer}`;
export const fillLayerIds = (layers: TileLayer[]) => layers.map((l) => layerId("fill", l.name));
export const isHexLayerId = (id: string) => LAYER_KINDS.some((k) => id.startsWith(`${k}-`));

/** MapLibre's layer maxzoom is exclusive; the highest layer gets none so it overzooms. */
function zoomRange(layer: TileLayer, layers: TileLayer[]): { minzoom: number; maxzoom?: number } {
  const top = Math.max(...layers.map((l) => l.maxzoom));
  return layer.maxzoom >= top ? { minzoom: layer.minzoom } : { minzoom: layer.minzoom, maxzoom: layer.maxzoom + 1 };
}

export function fillColorFor(o: ViewOptions): Expr {
  const pal = paletteFor(o.theme);
  if (o.view === "bivar") return bivarColor(pal);
  if (o.view === "priorities") return priorityColor(o.dims, o.weights, o.picks, pal);
  const dim = o.dims.find((d) => d.id === o.view);
  return scoreColor(o.view, dim ? rampFor(dim, pal) : pal.rampGood, pal.grey);
}

const showsNational = (view: ViewId) => view === "bivar" || view === "wb";
const stateFlag = (flag: string): Expr => ["boolean", ["feature-state", flag], false] as unknown as Expr;

export function buildLayers(o: ViewOptions, showUninhabited: boolean, conf: boolean, tileLayers: TileLayer[] = DEFAULT_TILE_LAYERS): LayerSpecification[] {
  const pal = paletteFor(o.theme);
  const layers: LayerSpecification[] = [];
  for (const tl of tileLayers) {
    const L = tl.name;
    const zoom = zoomRange(tl, tileLayers);
    const base = { source: SOURCE_ID, "source-layer": L, ...zoom };
    layers.push({
      id: layerId("fill", L),
      type: "fill",
      ...base,
      filter: inhabitedFilter(showUninhabited),
      paint: { "fill-color": fillColorFor(o), "fill-opacity": 0.85, "fill-outline-color": pal.outline },
    } as LayerSpecification);
    layers.push({
      id: layerId("hatch", L),
      type: "fill",
      ...base,
      filter: ["all", inhabitedFilter(showUninhabited), hatchFilter()] as unknown as FilterSpecification,
      layout: { visibility: conf ? "visible" : "none" },
      paint: { "fill-pattern": HATCH_IMAGE, "fill-opacity": 0.5 },
    } as LayerSpecification);
    layers.push({
      id: layerId("national", L),
      type: "line",
      ...base,
      filter: ["all", inhabitedFilter(showUninhabited), nationalFilter()] as unknown as FilterSpecification,
      layout: { visibility: showsNational(o.view) ? "visible" : "none" },
      paint: { "line-color": pal.national, "line-width": 0.6, "line-dasharray": [1, 3] },
    } as LayerSpecification);
    layers.push({
      id: layerId("hover", L),
      type: "line",
      ...base,
      paint: { "line-color": pal.hover, "line-width": ["case", stateFlag("hover"), 1.5, 0] },
    } as LayerSpecification);
    layers.push({
      id: layerId("halo", L),
      type: "line",
      ...base,
      paint: { "line-color": pal.halo, "line-width": ["case", stateFlag("selected"), 5, 0] },
    } as LayerSpecification);
    layers.push({
      id: layerId("selected", L),
      type: "line",
      ...base,
      paint: { "line-color": pal.selected, "line-width": ["case", stateFlag("selected"), 2.2, 0] },
    } as LayerSpecification);
  }
  return layers;
}

/** Re-style in place after a view, slider, toggle or theme change: no network request (SPEC §20.5). */
export function applyView(map: MapLibreMap, o: ViewOptions, showUninhabited: boolean, conf: boolean, tileLayers: TileLayer[] = DEFAULT_TILE_LAYERS): void {
  const pal = paletteFor(o.theme);
  const color = fillColorFor(o);
  for (const tl of tileLayers) {
    const L = tl.name;
    if (!map.getLayer(layerId("fill", L))) continue;
    map.setPaintProperty(layerId("fill", L), "fill-color", color);
    map.setPaintProperty(layerId("fill", L), "fill-outline-color", pal.outline);
    map.setFilter(layerId("fill", L), inhabitedFilter(showUninhabited));
    map.setFilter(layerId("hatch", L), ["all", inhabitedFilter(showUninhabited), hatchFilter()] as unknown as FilterSpecification);
    map.setLayoutProperty(layerId("hatch", L), "visibility", conf ? "visible" : "none");
    map.setFilter(layerId("national", L), ["all", inhabitedFilter(showUninhabited), nationalFilter()] as unknown as FilterSpecification);
    map.setLayoutProperty(layerId("national", L), "visibility", showsNational(o.view) ? "visible" : "none");
    map.setPaintProperty(layerId("national", L), "line-color", pal.national);
    map.setPaintProperty(layerId("hover", L), "line-color", pal.hover);
    map.setPaintProperty(layerId("halo", L), "line-color", pal.halo);
    map.setPaintProperty(layerId("selected", L), "line-color", pal.selected);
  }
}

/** Insert the hex layers under the basemap's labels so place names stay readable. */
export function firstSymbolLayerId(map: MapLibreMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
}

/**
 * For map.setStyle(url, { transformStyle }): carry the hex source and layers from the previous
 * (themed) style into the next basemap, under its first symbol layer, so a theme change never
 * re-adds the source or refetches tiles. Pure so it can be tested against the style spec.
 */
export function mergeStyleOnThemeChange(prev: StyleSpecification | undefined, next: StyleSpecification): StyleSpecification {
  if (!prev) return next;
  const hexSource = prev.sources?.[SOURCE_ID];
  const hexLayers = (prev.layers ?? []).filter((l) => isHexLayerId(l.id));
  if (!hexSource || !hexLayers.length) return next;
  const nextLayers = (next.layers ?? []).filter((l) => !isHexLayerId(l.id));
  const at = nextLayers.findIndex((l) => l.type === "symbol");
  const insertAt = at < 0 ? nextLayers.length : at;
  return {
    ...next,
    sources: { ...next.sources, [SOURCE_ID]: hexSource },
    layers: [...nextLayers.slice(0, insertAt), ...hexLayers, ...nextLayers.slice(insertAt)],
  };
}

export { paletteFor, type Palette };
