"use client";

// The MapLibre map (SPEC §9, §10). Creates the map once, registers the pmtiles protocol, adds
// the hex source and layer stack, re-styles in place when the view or sliders change, and swaps
// the basemap on a theme change while carrying the hex stack over (no tile refetch).
// Everything the person sees comes from the vector tile attributes; there is no API.

import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef } from "react";
import { INSPECT_MIN_ZOOM, MAP_MAX_ZOOM, MAP_MIN_ZOOM, tilesUrl } from "../lib/config";
import type { DimInfo } from "../lib/dims";
import { hatchImage } from "../lib/hatch";
import { paletteFor } from "../lib/palette";
import { applyView, buildLayers, DEFAULT_TILE_LAYERS, fillLayerIds, firstSymbolLayerId, HATCH_IMAGE, mergeStyleOnThemeChange, pickVisible, type TileLayer, type ViewOptions } from "../lib/style";
import { basemapStyleFor, THEME_EVENT, type Theme } from "../lib/theme";
import type { AppState } from "../lib/url";
import { getDomTheme } from "./useTheme";

export interface SelectedHex {
  sourceLayer: string;
  h3: string;
  props: Record<string, unknown>;
}

/** The hex under the pointer with the pointer's position inside the map container. */
export interface HoveredHex extends SelectedHex {
  x: number;
  y: number;
}

/** A request to fly somewhere (from search); `nonce` makes repeated picks of the same place fire. */
export interface FlyTo {
  lat: number;
  lng: number;
  zoom: number;
  nonce: number;
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
  /** one vector source per tile archive (manifest.tiles), id = archive name */
  archives: { id: string; key: string }[];
  tileLayers?: TileLayer[];
  dims: DimInfo[];
  state: AppState;
  flyTo?: FlyTo | null;
  onMove: (lat: number, lng: number, z: number) => void;
  onSelect: (hex: SelectedHex | null) => void;
  onHover?: (hex: HoveredHex | null) => void;
  onHint: (text: string | null) => void;
}

export default function MapView({ archives, tileLayers = DEFAULT_TILE_LAYERS, dims, state, flyTo, onMove, onSelect, onHover, onHint }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  const selectedRef = useRef<{ source: string; layer: string; id: string } | null>(null);
  const selectAtRef = useRef<((point: maplibregl.PointLike) => boolean) | null>(null);
  const stateRef = useRef(state);
  const cbRef = useRef({ onMove, onSelect, onHover, onHint });
  const themeRef = useRef<Theme>("light");
  useEffect(() => {
    // handlers registered once read the latest state and callbacks through refs
    stateRef.current = state;
    cbRef.current = { onMove, onSelect, onHover, onHint };
  });

  const options = (s: AppState): ViewOptions => ({ view: s.view, dims, weights: s.weights, picks: { pol: s.pol }, theme: themeRef.current });

  // create the map once; the initial view comes from the URL state parsed by MapApp
  useEffect(() => {
    if (!container.current || mapRef.current) return;
    ensureProtocol();
    const s = stateRef.current;
    themeRef.current = getDomTheme();
    const map = new maplibregl.Map({
      container: container.current,
      style: basemapStyleFor(themeRef.current),
      center: [s.lng, s.lat],
      zoom: s.z,
      minZoom: MAP_MIN_ZOOM,
      maxZoom: MAP_MAX_ZOOM,
      attributionControl: false,
    });
    // the OpenFreeMap style carries its own attribution (the BASEMAP_ATTRIBUTION text)
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __map?: maplibregl.Map }).__map = map; // browser-console debugging in dev only
    }

    // the hatch pattern is not part of the style JSON, so it is (re)added whenever a style asks
    // for it: at first load and after every basemap swap
    const addHatch = () => {
      if (!map.hasImage(HATCH_IMAGE)) map.addImage(HATCH_IMAGE, hatchImage(16, paletteFor(themeRef.current).hatch), { pixelRatio: 2 });
    };
    map.on("styleimagemissing", (e) => {
      if (e.id === HATCH_IMAGE) addHatch();
    });

    map.on("load", () => {
      addHatch();
      for (const a of archives) map.addSource(a.id, { type: "vector", url: `pmtiles://${tilesUrl(a.key)}`, promoteId: "h3" });
      const before = firstSymbolLayerId(map);
      const st = stateRef.current;
      for (const layer of buildLayers(options(st), st.inh, st.conf, tileLayers)) map.addLayer(layer, before);
      loadedRef.current = true;
      for (const id of fillLayerIds(tileLayers)) {
        map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
      }
    });

    // hover readout: feature-state on the hex under the pointer, one query per frame at most;
    // pointer devices only (a touch device selects on tap instead)
    const hoverable = typeof window.matchMedia === "function" && !window.matchMedia("(hover: none)").matches;
    let hovered: { source: string; layer: string; id: string } | null = null;
    let raf = 0;
    const clearHover = () => {
      if (hovered) map.setFeatureState({ source: hovered.source, sourceLayer: hovered.layer, id: hovered.id }, { hover: false });
      hovered = null;
      cbRef.current.onHover?.(null);
    };
    if (hoverable) {
      map.on("mousemove", (e) => {
        if (!loadedRef.current || raf) return;
        raf = window.requestAnimationFrame(() => {
          raf = 0;
          const f = pickVisible(map.queryRenderedFeatures(e.point, { layers: fillLayerIds(tileLayers).filter((id) => map.getLayer(id)) }), map.getZoom(), tileLayers);
          if (!f) {
            if (hovered) clearHover();
            return;
          }
          const h3 = String(f.properties.h3 ?? "");
          const sourceLayer = String(f.sourceLayer ?? "");
          if (!hovered || hovered.id !== h3) {
            if (hovered) map.setFeatureState({ source: hovered.source, sourceLayer: hovered.layer, id: hovered.id }, { hover: false });
            hovered = { source: String(f.source), layer: sourceLayer, id: h3 };
            map.setFeatureState({ source: String(f.source), sourceLayer, id: h3 }, { hover: true });
          }
          cbRef.current.onHover?.({ sourceLayer, h3, props: f.properties as Record<string, unknown>, x: e.point.x, y: e.point.y });
        });
      });
      map.on("mouseout", clearHover);
      map.on("dragstart", clearHover);
    }

    // theme change: swap the basemap, carry the hex stack over, recolour with the new palette
    const onTheme = (e: Event) => {
      const theme = (e as CustomEvent<Theme>).detail;
      if (theme === themeRef.current || !loadedRef.current) return;
      themeRef.current = theme;
      if (map.hasImage(HATCH_IMAGE)) map.removeImage(HATCH_IMAGE);
      map.once("style.load", () => applyView(map, options(stateRef.current), stateRef.current.inh, stateRef.current.conf, tileLayers));
      map.setStyle(basemapStyleFor(theme), { transformStyle: (prev, next) => mergeStyleOnThemeChange(prev, next) });
    };
    window.addEventListener(THEME_EVENT, onTheme);

    map.on("error", (e) => {
      const msg = (e as { error?: { message?: string } }).error?.message ?? "";
      if (msg) cbRef.current.onHint(`Map error: ${msg}`);
    });

    map.on("moveend", () => {
      const c = map.getCenter();
      cbRef.current.onMove(c.lat, c.lng, map.getZoom());
    });

    // select the hex under a screen point (a click, or the target of a search fly-to)
    const selectAt = (point: maplibregl.PointLike): boolean => {
      const f = pickVisible(map.queryRenderedFeatures(point, { layers: fillLayerIds(tileLayers).filter((id) => map.getLayer(id)) }), map.getZoom(), tileLayers);
      if (selectedRef.current) {
        map.setFeatureState({ source: selectedRef.current.source, sourceLayer: selectedRef.current.layer, id: selectedRef.current.id }, { selected: false });
        selectedRef.current = null;
      }
      if (!f) {
        cbRef.current.onSelect(null);
        return false;
      }
      const h3 = String(f.properties.h3 ?? "");
      const sourceLayer = String(f.sourceLayer ?? "");
      if (h3) {
        map.setFeatureState({ source: String(f.source), sourceLayer, id: h3 }, { selected: true });
        selectedRef.current = { source: String(f.source), layer: sourceLayer, id: h3 };
      }
      cbRef.current.onHint(null);
      cbRef.current.onSelect({ sourceLayer, h3, props: f.properties as Record<string, unknown> });
      return true;
    };
    selectAtRef.current = selectAt;

    map.on("click", (e) => {
      if (!loadedRef.current) return;
      if (map.getZoom() < INSPECT_MIN_ZOOM) {
        cbRef.current.onHint("Zoom in to inspect a hex (hexes are a few pixels wide here).");
        return;
      }
      selectAt(e.point);
    });

    return () => {
      window.removeEventListener(THEME_EVENT, onTheme);
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // search result: fly there, then select the hex under the point once tiles are in
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyTo) return;
    const target: [number, number] = [flyTo.lng, flyTo.lat];
    map.flyTo({ center: target, zoom: flyTo.zoom, duration: 1400, essential: true });
    const onIdle = () => {
      const hit = selectAtRef.current?.(map.project(target));
      if (hit === false) cbRef.current.onHint("No inhabited hex here; the nearest coloured hexes are the data.");
    };
    map.once("idle", onIdle);
    return () => {
      map.off("idle", onIdle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyTo?.nonce]);

  // restyle in place on view / weights / picks / toggles (SPEC §20.5: no rebuild, no request)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applyView(map, options(state), state.inh, state.conf, tileLayers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.view, state.weights, state.pol, state.inh, state.conf, dims]);

  return <div ref={container} className="h-full w-full" role="application" aria-label="Map of climate exposure and wellbeing" />;
}
