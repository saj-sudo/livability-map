// The hex layer stack (SPEC §9.3): one vector source with layers hex4 (z2-4) and hex5 (z5+),
// a fill per view, a hatch overlay for reduced confidence, a dashed outline for national
// wellbeing fallback, and a selection outline driven by feature-state.

import type { FilterSpecification, LayerSpecification, Map as MapLibreMap } from "maplibre-gl";
import { HEX_SPLIT_ZOOM, MAP_MIN_ZOOM } from "./config";
import type { DimInfo } from "./dims";
import { bivarColor, hatchFilter, inhabitedFilter, nationalFilter, priorityColor, rampFor, scoreColor, type Expr, type Picks, type Weights } from "./expressions";
import { RAMP_GOOD } from "./palette";
import type { ViewId } from "./url";

export const SOURCE_ID = "hexes";
export const SOURCE_LAYERS = ["hex4", "hex5"] as const;
export type SourceLayer = (typeof SOURCE_LAYERS)[number];
export type LayerKind = "fill" | "hatch" | "national" | "selected";

export interface ViewOptions {
  view: ViewId;
  dims: DimInfo[];
  weights: Weights;
  picks: Picks;
}

export const layerId = (kind: LayerKind, layer: SourceLayer) => `${kind}-${layer}`;
export const fillLayerIds = () => SOURCE_LAYERS.map((l) => layerId("fill", l));

function zoomRange(layer: SourceLayer): { minzoom: number; maxzoom?: number } {
  return layer === "hex4" ? { minzoom: MAP_MIN_ZOOM, maxzoom: HEX_SPLIT_ZOOM } : { minzoom: HEX_SPLIT_ZOOM };
}

export function fillColorFor(o: ViewOptions): Expr {
  if (o.view === "bivar") return bivarColor();
  if (o.view === "priorities") return priorityColor(o.dims, o.weights, o.picks);
  const dim = o.dims.find((d) => d.id === o.view);
  return scoreColor(o.view, dim ? rampFor(dim) : RAMP_GOOD);
}

const showsNational = (view: ViewId) => view === "bivar" || view === "wb";

export function buildLayers(o: ViewOptions, showUninhabited: boolean, conf: boolean): LayerSpecification[] {
  const layers: LayerSpecification[] = [];
  for (const L of SOURCE_LAYERS) {
    const zoom = zoomRange(L);
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
export function applyView(map: MapLibreMap, o: ViewOptions, showUninhabited: boolean, conf: boolean): void {
  const color = fillColorFor(o);
  for (const L of SOURCE_LAYERS) {
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
