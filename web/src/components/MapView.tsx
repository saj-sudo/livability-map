"use client";

// The MapLibre map (SPEC §9, §10). Creates the map once, registers the pmtiles protocol, adds
// the hex source and layer stack, and re-styles in place when the view or sliders change.
// Everything the person sees comes from the vector tile attributes; there is no API.

import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef } from "react";
import { BASEMAP_ATTRIBUTION, BASEMAP_STYLE, INSPECT_MIN_ZOOM, MAP_MAX_ZOOM, MAP_MIN_ZOOM, tilesUrl } from "../lib/config";
import type { DimInfo } from "../lib/dims";
import { hatchImage } from "../lib/hatch";
import { applyView, buildLayers, DEFAULT_TILE_LAYERS, fillLayerIds, firstSymbolLayerId, SOURCE_ID, type TileLayer, type ViewOptions } from "../lib/style";
import type { AppState } from "../lib/url";

export interface SelectedHex {
  sourceLayer: string;
  h3: string;
  props: Record<string, unknown>;
}

let protocolRegistered = false;
function ensureProtocol() {
  if (protocolRegistered) return;
  // MapLibre v6 resolves its worker relative to its own module URL, which a bundler rewrites, so
  // point it at the copy scripts/copy-worker.mjs puts in public/ (SPEC §15.13).
  maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");
  const protocol = new Protocol({ metadata: true });
  maplibregl.addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}

interface Props {
  tilesKey: string;
  tileLayers?: TileLayer[];
  dims: DimInfo[];
  state: AppState;
  onMove: (lat: number, lng: number, z: number) => void;
  onSelect: (hex: SelectedHex | null) => void;
  onHint: (text: string | null) => void;
}

export default function MapView({ tilesKey, tileLayers = DEFAULT_TILE_LAYERS, dims, state, onMove, onSelect, onHint }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const selectedRef = useRef<{ layer: string; id: string } | null>(null);
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state; // handlers registered once read the latest state through the ref
  });

  const options = (s: AppState): ViewOptions => ({ view: s.view, dims, weights: s.weights, picks: { pol: s.pol, race: s.race } });

  // create the map once; the initial view comes from the URL state parsed by MapApp
  useEffect(() => {
    if (!container.current || mapRef.current) return;
    ensureProtocol();
    const s = stateRef.current;
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      center: [s.lng, s.lat],
      zoom: s.z,
      minZoom: MAP_MIN_ZOOM,
      maxZoom: MAP_MAX_ZOOM,
      attributionControl: false,
    });
    map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: BASEMAP_ATTRIBUTION }), "bottom-right");
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __map?: maplibregl.Map }).__map = map; // browser-console debugging in dev only
    }

    map.on("load", () => {
      map.addImage("hatch", hatchImage(), { pixelRatio: 2 });
      map.addSource(SOURCE_ID, { type: "vector", url: `pmtiles://${tilesUrl(tilesKey)}`, promoteId: "h3" });
      const before = firstSymbolLayerId(map);
      const st = stateRef.current;
      for (const layer of buildLayers(options(st), st.inh, st.conf, tileLayers)) map.addLayer(layer, before);
      loadedRef.current = true;
      for (const id of fillLayerIds(tileLayers)) {
        map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
      }
    });

    map.on("error", (e) => {
      const msg = (e as { error?: { message?: string } }).error?.message ?? "";
      if (msg) onHint(`Map error: ${msg}`);
    });

    map.on("moveend", () => {
      const c = map.getCenter();
      onMove(c.lat, c.lng, map.getZoom());
    });

    map.on("click", (e) => {
      if (!loadedRef.current) return;
      if (map.getZoom() < INSPECT_MIN_ZOOM) {
        onHint("Zoom in to inspect a hex (hexes are a few pixels wide here).");
        return;
      }
      const f = map.queryRenderedFeatures(e.point, { layers: fillLayerIds(tileLayers).filter((id) => map.getLayer(id)) })[0];
      if (selectedRef.current) {
        map.setFeatureState({ source: SOURCE_ID, sourceLayer: selectedRef.current.layer, id: selectedRef.current.id }, { selected: false });
        selectedRef.current = null;
      }
      if (!f) {
        onSelect(null);
        return;
      }
      const h3 = String(f.properties.h3 ?? "");
      const sourceLayer = String(f.sourceLayer ?? "");
      if (h3) {
        map.setFeatureState({ source: SOURCE_ID, sourceLayer, id: h3 }, { selected: true });
        selectedRef.current = { layer: sourceLayer, id: h3 };
      }
      onHint(null);
      onSelect({ sourceLayer, h3, props: f.properties as Record<string, unknown> });
    });

    return () => {
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // restyle in place on view / weights / picks / toggles (SPEC §20.5: no rebuild, no request)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applyView(map, options(state), state.inh, state.conf, tileLayers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.view, state.weights, state.pol, state.race, state.inh, state.conf, dims]);

  return <div ref={container} className="h-full w-full" role="application" aria-label="Map of climate exposure and wellbeing" />;
}
