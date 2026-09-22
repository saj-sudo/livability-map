// The hex layer stack (SPEC §9.3): one vector source with layers hex4 (z2-4) and hex5 (z5+),
// a fill per view, a hatch overlay for reduced confidence, a dashed outline for national
// wellbeing fallback, and a selection outline driven by feature-state.

import type { FilterSpecification, LayerSpecification, Map as MapLibreMap } from "maplibre-gl";
import type { DimInfo } from "./dims";
import { bivarColor, hatchFilter, inhabitedFilter, nationalFilter, priorityColor, rampFor, scoreColor, type Expr, type Picks, type Weights } from "./expressions";
import { RAMP_GOOD } from "./palette";
import type { ViewId } from "./url";

export const SOURCE_ID = "hexes";
export type LayerKind = "fill" | "hatch" | "national" | "selected";

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
}

export const layerId = (kind: LayerKind, layer: string) => `${kind}-${layer}`;
export const fillLayerIds = (layers: TileLayer[]) => layers.map((l) => layerId("fill", l.name));

/** MapLibre's layer maxzoom is exclusive; the highest layer gets none so it overzooms. */
function zoomRange(layer: TileLayer, layers: TileLayer[]): { minzoom: number; maxzoom?: number } {
  const top = Math.max(...layers.map((l) => l.maxzoom));
  return layer.maxzoom >= top ? { minzoom: layer.minzoom } : { minzoom: layer.minzoom, maxzoom: layer.maxzoom + 1 };
}

export function fillColorFor(o: ViewOptions): Expr {
  if (o.view === "bivar") return bivarColor();
  if (o.view === "priorities") return priorityColor(o.dims, o.weights, o.picks);
  const dim = o.dims.find((d) => d.id === o.view);
  return scoreColor(o.view, dim ? rampFor(dim) : RAMP_GOOD);
}

const showsNational = (view: ViewId) => view === "bivar" || view === "wb";

export function buildLayers(o: ViewOptions, showUninhabited: boolean, conf: boolean, tileLayers: TileLayer[] = DEFAULT_TILE_LAYERS): LayerSpecification[] {
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
      paint: { "fill-color": fillColorFor(o), "fill-opacity": 0.82, "fill-outline-color": "rgba(0,0,0,0.12)" },
    } as LayerSpecification);
    layers.push({
      id: layerId("hatch", L),
      type: "fill",
      ...base,
      filter: ["all", inhabitedFilter(showUninhabited), hatchFilter()] as unknown as FilterSpecification,
      layout: { visibility: conf ? "visible" : "none" },
      paint: { "fill-pattern": "hatch", "fill-opacity": 0.55 },
    } as LayerSpecification);
    layers.push({
      id: layerId("national", L),
      type: "line",
      ...base,
      filter: ["all", inhabitedFilter(showUninhabited), nationalFilter()] as unknown as FilterSpecification,
      layout: { visibility: showsNational(o.view) ? "visible" : "none" },
      paint: { "line-color": "#444", "line-width": 0.9, "line-dasharray": [2, 2] },
    } as LayerSpecification);
    layers.push({
      id: layerId("selected", L),
      type: "line",
      ...base,
      paint: { "line-color": "#111", "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.5, 0] },
    } as LayerSpecification);
  }
  return layers;
}

/** Re-style in place after a view, slider or toggle change: no network request (SPEC §20.5). */
export function applyView(map: MapLibreMap, o: ViewOptions, showUninhabited: boolean, conf: boolean, tileLayers: TileLayer[] = DEFAULT_TILE_LAYERS): void {
  const color = fillColorFor(o);
  for (const tl of tileLayers) {
    const L = tl.name;
    if (!map.getLayer(layerId("fill", L))) continue;
    map.setPaintProperty(layerId("fill", L), "fill-color", color);
    map.setFilter(layerId("fill", L), inhabitedFilter(showUninhabited));
    map.setFilter(layerId("hatch", L), ["all", inhabitedFilter(showUninhabited), hatchFilter()] as unknown as FilterSpecification);
    map.setLayoutProperty(layerId("hatch", L), "visibility", conf ? "visible" : "none");
    map.setFilter(layerId("national", L), ["all", inhabitedFilter(showUninhabited), nationalFilter()] as unknown as FilterSpecification);
    map.setLayoutProperty(layerId("national", L), "visibility", showsNational(o.view) ? "visible" : "none");
  }
}

/** Insert the hex layers under the basemap's labels so place names stay readable. */
export function firstSymbolLayerId(map: MapLibreMap): string | undefined {
  return map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id;
}
