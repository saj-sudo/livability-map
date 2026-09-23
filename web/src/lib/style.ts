// The hex layer stack (SPEC §9.1, §9.3): one vector source per tile archive and one layer group
// per tile layer in the manifest (hex4 z2-4, hex5 z5-7, hex6 z8-9, hex7 z10-13 where built), in
// resolution order. A layer that overzooms keeps drawing under the finer layers; its cells that a
// finer layer replaced (`ref`) fade out from that layer's first zoom so colours never double up.
// Each group has a fill per view, a hatch overlay for
// reduced confidence, a dashed outline for national wellbeing fallback, a hover outline and a
// haloed selection outline driven by feature-state. Colours come from the theme's palette.

import type { FilterSpecification, LayerSpecification, Map as MapLibreMap, StyleSpecification } from "maplibre-gl";
import type { DimInfo } from "./dims";
import { bivarColor, hatchFilter, inhabitedFilter, nationalFilter, priorityColor, rampFor, scoreColor, type Expr, type Picks, type Weights } from "./expressions";
import { DEFAULT_TILE_LAYERS, type TileLayer } from "./layers";
import { paletteFor, type Palette } from "./palette";
import type { Theme } from "./theme";
import type { ViewId } from "./url";

export const SOURCE_ID = "hexes";
export const HATCH_IMAGE = "hatch";
export const LAYER_KINDS = ["fill", "hatch", "national", "hover", "halo", "selected"] as const;
export type LayerKind = (typeof LAYER_KINDS)[number];

export { DEFAULT_TILE_LAYERS, type TileLayer };

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

/** Every MapLibre source the layers read (one per archive). */
export const hexSourceIds = (layers: TileLayer[]): string[] => [...new Set(layers.map((l) => l.source))];

/** MapLibre's layer maxzoom is exclusive; a layer that overzooms gets none. */
function zoomRange(layer: TileLayer): { minzoom: number; maxzoom?: number } {
  return layer.overzoom ? { minzoom: layer.minzoom } : { minzoom: layer.minzoom, maxzoom: layer.maxzoom + 1 };
}

/** First zoom of the next finer layer, when this layer is still drawn there (it overzooms). */
function hideRefinedFrom(layer: TileLayer, layers: TileLayer[]): number | undefined {
  if (!layer.overzoom) return undefined;
  const finer = layers.filter((l) => l.res > layer.res).map((l) => l.minzoom);
  return finer.length ? Math.min(...finer) : undefined;
}

/** Opacity that drops to 0 for refined cells (`ref`) from zoom `from` on (SPEC §9.1). */
function refinedOpacity(base: number, from: number | undefined): number | Expr {
  if (from === undefined) return base;
  return ["step", ["zoom"], base, from, ["case", ["==", ["get", "ref"], true], 0, base]] as unknown as Expr;
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
    const zoom = zoomRange(tl);
    const from = hideRefinedFrom(tl, tileLayers);
    const line = refinedOpacity(1, from);
    const base = { source: tl.source, "source-layer": L, ...zoom };
    layers.push({
      id: layerId("fill", L),
      type: "fill",
      ...base,
      filter: inhabitedFilter(showUninhabited),
      paint: { "fill-color": fillColorFor(o), "fill-opacity": refinedOpacity(0.85, from), "fill-outline-color": pal.outline },
    } as LayerSpecification);
    layers.push({
      id: layerId("hatch", L),
      type: "fill",
      ...base,
      filter: ["all", inhabitedFilter(showUninhabited), hatchFilter()] as unknown as FilterSpecification,
      layout: { visibility: conf ? "visible" : "none" },
      paint: { "fill-pattern": HATCH_IMAGE, "fill-opacity": refinedOpacity(0.5, from) },
    } as LayerSpecification);
    layers.push({
      id: layerId("national", L),
      type: "line",
      ...base,
      filter: ["all", inhabitedFilter(showUninhabited), nationalFilter()] as unknown as FilterSpecification,
      layout: { visibility: showsNational(o.view) ? "visible" : "none" },
      paint: { "line-color": pal.national, "line-width": 0.6, "line-dasharray": [1, 3], "line-opacity": line },
    } as LayerSpecification);
    layers.push({
      id: layerId("hover", L),
      type: "line",
      ...base,
      paint: { "line-color": pal.hover, "line-width": ["case", stateFlag("hover"), 1.5, 0], "line-opacity": line },
    } as LayerSpecification);
    layers.push({
      id: layerId("halo", L),
      type: "line",
      ...base,
      paint: { "line-color": pal.halo, "line-width": ["case", stateFlag("selected"), 5, 0], "line-opacity": line },
    } as LayerSpecification);
    layers.push({
      id: layerId("selected", L),
      type: "line",
      ...base,
      paint: { "line-color": pal.selected, "line-width": ["case", stateFlag("selected"), 2.2, 0], "line-opacity": line },
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
  const hexLayers = (prev.layers ?? []).filter((l) => isHexLayerId(l.id));
  const ids = [...new Set(hexLayers.map((l) => (l as { source?: string }).source).filter((s): s is string => !!s))];
  const hexSources = Object.fromEntries(ids.filter((id) => prev.sources?.[id]).map((id) => [id, prev.sources[id]]));
  if (!Object.keys(hexSources).length || !hexLayers.length) return next;
  const nextLayers = (next.layers ?? []).filter((l) => !isHexLayerId(l.id));
  const at = nextLayers.findIndex((l) => l.type === "symbol");
  const insertAt = at < 0 ? nextLayers.length : at;
  return {
    ...next,
    sources: { ...next.sources, ...hexSources },
    layers: [...nextLayers.slice(0, insertAt), ...hexLayers, ...nextLayers.slice(insertAt)],
  };
}

export { paletteFor, type Palette };
