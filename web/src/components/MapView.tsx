"use client";

// The MapLibre map (SPEC §9, §10). Creates the map once, registers the pmtiles protocol, adds
// the hex source and layer stack, re-styles in place when the view or sliders change, and swaps
// the basemap on a theme change while carrying the hex stack over (no tile refetch).
// Everything the person sees comes from the vector tile attributes; there is no API.
// The data never waits on the basemap: hexes are added as soon as a style is parsed, and a
// basemap that fails or stalls is replaced by a plain background (§13.41, lib/mapHealth.ts).

import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useRef } from "react";
import { INSPECT_MIN_ZOOM, MAP_MAX_ZOOM, MAP_MIN_ZOOM, tilesUrl } from "../lib/config";
import type { DimInfo } from "../lib/dims";
import { hatchImage } from "../lib/hatch";
import { classifyError, fallbackStyle, NO_PROBLEMS, noteProblem, OTHER_ERROR_HINT, STYLE_TIMEOUT_MS, type ErrorKind, type MapProblems } from "../lib/mapHealth";
import { paletteFor } from "../lib/palette";
import type { PlaceRef } from "../lib/place";
import { diffOutlines, type OutlineKey } from "../lib/selection";
import { applyView, buildLayers, DEFAULT_TILE_LAYERS, fillLayerIds, firstSymbolLayerId, HATCH_IMAGE, mergeStyleOnThemeChange, pickVisible, type TileLayer, type ViewOptions } from "../lib/style";
import { basemapStyleFor, THEME_EVENT, type Theme } from "../lib/theme";
import type { AppState } from "../lib/url";
import { getDomTheme } from "./useTheme";

export interface SelectedHex {
  /** the vector source (tile archive) the hex was picked from; needed to outline it */
  source?: string;
  sourceLayer: string;
  h3: string;
  props: Record<string, unknown>;
  /** the search result that led here, so the panel can keep its name */
  place?: PlaceRef;
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
  place?: PlaceRef;
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
  /** the selected places (A, then B while comparing); MapView outlines exactly these */
  selection?: SelectedHex[];
  onMove: (lat: number, lng: number, z: number) => void;
  onSelect: (hex: SelectedHex | null) => void;
  onHover?: (hex: HoveredHex | null) => void;
  onHint: (text: string | null) => void;
  /** dependencies that failed (basemap, tile archives); MapApp shows a persistent notice */
  onProblems?: (problems: MapProblems) => void;
}

/** Where each selected hex is outlined; a hex without a known source cannot be outlined. */
const outlineKeys = (sel: SelectedHex[]): OutlineKey[] => sel.filter((h) => h.source && h.h3).map((h) => ({ source: h.source!, sourceLayer: h.sourceLayer, id: h.h3 }));

export default function MapView({ archives, tileLayers = DEFAULT_TILE_LAYERS, dims, state, flyTo, selection = [], onMove, onSelect, onHover, onHint, onProblems }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loadedRef = useRef(false);
  // outlines currently drawn (feature-state `selected`), so they can be cleared exactly
  const outlinedRef = useRef<OutlineKey[]>([]);
  const selectionRef = useRef<OutlineKey[]>([]);
  const selectAtRef = useRef<((point: maplibregl.PointLike, place?: PlaceRef) => boolean) | null>(null);
  const stateRef = useRef(state);
  const cbRef = useRef({ onMove, onSelect, onHover, onHint, onProblems });
  const themeRef = useRef<Theme>("light");
  const basemapDownRef = useRef(false);
  useEffect(() => {
    // handlers registered once read the latest state and callbacks through refs
    stateRef.current = state;
    cbRef.current = { onMove, onSelect, onHover, onHint, onProblems };
  });

  // draw the selection outlines from the selection prop: clear what is no longer selected, set
  // what is new (the panel and the map always agree)
  const syncOutlines = (map: maplibregl.Map, force = false) => {
    if (!loadedRef.current) return;
    const next = selectionRef.current;
    const { clear, set } = diffOutlines(outlinedRef.current, next);
    const state = (k: OutlineKey, selected: boolean) => {
      if (map.getSource(k.source)) map.setFeatureState({ source: k.source, sourceLayer: k.sourceLayer, id: k.id }, { selected });
    };
    for (const k of clear) state(k, false);
    // force: after a style (re)load every outline is drawn again, not only the new ones
    for (const k of force ? next : set) state(k, true);
    outlinedRef.current = [...next];
    // what is outlined, readable from the DOM (the e2e test checks panel and map agree)
    if (container.current) container.current.dataset.outlined = next.map((k) => k.id).join(",");
  };

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

    let problems = NO_PROBLEMS;
    const report = (k: ErrorKind) => {
      const next = noteProblem(problems, k);
      if (next === problems) return;
      problems = next;
      cbRef.current.onProblems?.(problems);
    };
    // the basemap style failed or stalled: draw the hexes on a plain background instead
    const switchToPlainBackground = () => {
      if (basemapDownRef.current) return;
      basemapDownRef.current = true;
      report({ kind: "basemap" });
      map.setStyle(fallbackStyle(themeRef.current));
    };
    const styleTimer = window.setTimeout(() => {
      if (!loadedRef.current) switchToPlainBackground();
    }, STYLE_TIMEOUT_MS);

    // the hex sources and layers go in once, on the first style that parses (style.load, not
    // load: load also waits for every basemap tile); theme swaps carry them over
    const addData = () => {
      if (loadedRef.current) return;
      window.clearTimeout(styleTimer);
      addHatch();
      for (const a of archives) map.addSource(a.id, { type: "vector", url: `pmtiles://${tilesUrl(a.key)}`, promoteId: "h3" });
      const before = firstSymbolLayerId(map);
      const st = stateRef.current;
      for (const layer of buildLayers(options(st), st.inh, st.conf, tileLayers)) map.addLayer(layer, before);
      loadedRef.current = true;
      syncOutlines(map, true);
      for (const id of fillLayerIds(tileLayers)) {
        map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
      }
    };
    map.on("style.load", addData);

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
      map.once("style.load", () => {
        applyView(map, options(stateRef.current), stateRef.current.inh, stateRef.current.conf, tileLayers);
        syncOutlines(map, true);
      });
      const style = basemapDownRef.current ? fallbackStyle(theme) : basemapStyleFor(theme);
      map.setStyle(style, { transformStyle: (prev, next) => mergeStyleOnThemeChange(prev, next) });
    };
    window.addEventListener(THEME_EVENT, onTheme);

    const archiveIds = archives.map((a) => a.id);
    map.on("error", (e) => {
      const k = classifyError(e as Parameters<typeof classifyError>[0], archiveIds);
      if (k.kind === "tiles") return report(k);
      if (k.kind === "basemap") {
        // before the data is up, a basemap failure means its style: switch to the plain
        // background. Later, a missing basemap tile or glyph only leaves a gap behind the hexes.
        if (!loadedRef.current) switchToPlainBackground();
        return;
      }
      // the raw MapLibre message is for developers: console only, plain words on screen
      const msg = (e as { error?: { message?: string } }).error?.message ?? "";
      if (msg) {
        console.warn("map error:", msg);
        cbRef.current.onHint(OTHER_ERROR_HINT);
      }
    });

    map.on("moveend", () => {
      const c = map.getCenter();
      cbRef.current.onMove(c.lat, c.lng, map.getZoom());
    });

    // select the hex under a screen point (a click, or the target of a search fly-to)
    // (the outline itself follows the selection prop, see syncOutlines)
    const selectAt = (point: maplibregl.PointLike, place?: PlaceRef): boolean => {
      const f = pickVisible(map.queryRenderedFeatures(point, { layers: fillLayerIds(tileLayers).filter((id) => map.getLayer(id)) }), map.getZoom(), tileLayers);
      if (!f) {
        cbRef.current.onSelect(null);
        return false;
      }
      const h3 = String(f.properties.h3 ?? "");
      const sourceLayer = String(f.sourceLayer ?? "");
      cbRef.current.onHint(null);
      cbRef.current.onSelect({ source: String(f.source), sourceLayer, h3, props: f.properties as Record<string, unknown>, ...(place ? { place } : {}) });
      return true;
    };
    selectAtRef.current = selectAt;

    map.on("click", (e) => {
      if (!loadedRef.current) return;
      if (map.getZoom() < INSPECT_MIN_ZOOM) {
        cbRef.current.onHint("Zoom in to see a place's details; the hexagons are too small to pick at this zoom.");
        return;
      }
      selectAt(e.point);
    });

    return () => {
      window.clearTimeout(styleTimer);
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
    // not `essential`: MapLibre then honours prefers-reduced-motion and jumps instead of flying
    map.flyTo({ center: target, zoom: flyTo.zoom, duration: 1400 });
    const onIdle = () => {
      const hit = selectAtRef.current?.(map.project(target), flyTo.place);
      if (hit === false) cbRef.current.onHint("There is no data right at this spot. Try a coloured hexagon nearby.");
    };
    map.once("idle", onIdle);
    return () => {
      map.off("idle", onIdle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyTo?.nonce]);

  // keep the outlines in step with the selection (closing the panel, swapping, re-picking)
  const selectionKey = outlineKeys(selection)
    .map((k) => `${k.source}/${k.sourceLayer}/${k.id}`)
    .join(",");
  useEffect(() => {
    selectionRef.current = outlineKeys(selection);
    const map = mapRef.current;
    if (map) syncOutlines(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectionKey]);

  // restyle in place on view / weights / picks / toggles (SPEC §20.5: no rebuild, no request)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    applyView(map, options(state), state.inh, state.conf, tileLayers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.view, state.weights, state.pol, state.inh, state.conf, dims]);

  return <div ref={container} className="h-full w-full" role="application" aria-label="Map of climate exposure and wellbeing" />;
}
