"use client";

// Client shell: owns the URL-backed app state (SPEC §10), the selected hex, the fly-to
// request from search, the hover readout and the panels. The map itself is loaded without
// SSR because MapLibre needs the DOM and WebGL2.

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ComparePanel from "./ComparePanel";
import Inspector from "./Inspector";
import Intro from "./Intro";
import Panel from "./Panel";
import Search from "./Search";
import Sheet from "./Sheet";
import Tooltip from "./Tooltip";
import { PHONE_QUERY, useMediaQuery } from "./useMediaQuery";
import { archivesFrom, tileLayersFrom } from "../lib/layers";
import type { FlyTo, HoveredHex, SelectedHex } from "./MapView";
import type { ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { shouldShowIntro } from "../lib/intro";
import { zoomFor, type Place } from "../lib/search";
import type { Snap } from "../lib/sheet";
import { DEFAULT_STATE, parseState, writeUrl, type AppState } from "../lib/url";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="absolute inset-0 grid place-items-center text-muted">Loading map…</div> });

interface Props {
  manifest: ClientManifest;
  dims: DimInfo[];
}

const HINT_MS = 4000;

/** bivariate class of the hovered hex for the legend (0 = no data) */
const hoverBivar = (h: HoveredHex): number => (typeof h.props.bivar === "number" ? h.props.bivar : 0);

export default function MapApp({ manifest, dims }: Props) {
  const [state, setState] = useState<AppState>(DEFAULT_STATE);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<SelectedHex | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<FlyTo | null>(null);
  const [hover, setHover] = useState<HoveredHex | null>(null);
  // compare: a second hex chosen after "Compare with another place" (session-only, not in the URL)
  const [compare, setCompare] = useState<SelectedHex | null>(null);
  const [picking, setPicking] = useState(false);
  const [searchSlot, setSearchSlot] = useState<HTMLElement | null>(null);
  const [helpSlot, setHelpSlot] = useState<HTMLElement | null>(null);
  const [intro, setIntro] = useState(false);
  // phone layout: one bottom sheet with two tabs instead of floating panels
  const phone = useMediaQuery(PHONE_QUERY);
  const [snap, setSnap] = useState<Snap>("peek");
  const [tab, setTab] = useState<"layers" | "place">("layers");
  const urlTimer = useRef<number | null>(null);

  // read the URL once on the client after hydration (no useSearchParams: static export). The
  // server prerenders the default state, so this has to be a post-mount update.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(parseState(window.location.search));
    setReady(true);
    setSearchSlot(document.getElementById("search-slot"));
    setHelpSlot(document.getElementById("help-slot"));
    setIntro(shouldShowIntro(window.localStorage));
  }, []);

  // write the URL on every state change, debounced so map moves do not thrash history
  useEffect(() => {
    if (!ready) return;
    if (urlTimer.current) window.clearTimeout(urlTimer.current);
    urlTimer.current = window.setTimeout(() => writeUrl(state), 150);
  }, [state, ready]);

  // hints are transient: clear after a few seconds so a stale message never sticks
  useEffect(() => {
    if (!hint) return;
    const t = window.setTimeout(() => setHint(null), HINT_MS);
    return () => window.clearTimeout(t);
  }, [hint]);

  const onMove = useCallback((lat: number, lng: number, z: number) => setState((s) => ({ ...s, lat, lng, z })), []);
  const update = useCallback((patch: Partial<AppState>) => setState((s) => ({ ...s, ...patch })), []);
  const onPick = useCallback((p: Place) => setFlyTo({ lat: p.lat, lng: p.lng, zoom: zoomFor(p), nonce: Date.now() }), []);

  // a click (or a search landing) either selects, or fills the second slot while picking
  const onSelect = useCallback(
    (hex: SelectedHex | null) => {
      if (picking && hex) {
        if (hex.h3 !== selected?.h3) {
          setCompare(hex);
          setPicking(false);
          setHint(null);
        }
        return;
      }
      setSelected(hex);
      if (!hex) {
        setCompare(null);
        setPicking(false);
      } else {
        setTab("place");
        setSnap((s) => (s === "peek" ? "half" : s));
      }
    },
    [picking, selected],
  );
  const startPicking = useCallback(() => {
    setPicking(true);
    setHint("Click or search a second place to compare");
  }, []);

  // SPEC §9.1: one source per tile archive, layers in resolution order with their plan flags
  const tileLayers = useMemo(() => tileLayersFrom(manifest.tiles), [manifest.tiles]);
  const archives = useMemo(() => {
    const a = archivesFrom(manifest.tiles);
    return a.length ? a : [{ id: "hexes", key: "hexes.pmtiles" }];
  }, [manifest.tiles]);

  // the inspector or the comparison for the selected hex; floats on desktop, sits in the sheet on a phone
  const place =
    selected && compare ? (
      <ComparePanel
        a={selected}
        b={compare}
        manifest={manifest}
        dims={dims}
        state={state}
        onSwap={() => {
          setSelected(compare);
          setCompare(selected);
        }}
        onRepick={startPicking}
        onClose={() => setCompare(null)}
        embedded={phone}
      />
    ) : selected ? (
      <Inspector hex={selected} manifest={manifest} dims={dims} state={state} onClose={() => setSelected(null)} onCompare={startPicking} embedded={phone} />
    ) : null;

  return (
    <div className="map-shell">
      {ready && <MapView archives={archives} tileLayers={tileLayers} dims={dims} state={state} flyTo={flyTo} onMove={onMove} onSelect={onSelect} onHover={setHover} onHint={setHint} />}
      {searchSlot && createPortal(<Search onPick={onPick} className="mx-auto w-full max-w-md" />, searchSlot)}
      {helpSlot &&
        createPortal(
          <button type="button" onClick={() => setIntro(true)} aria-label="How to read this map" title="How to read this map" className="grid h-8 w-8 place-items-center rounded-panel text-muted hover:bg-rule/60 hover:text-ink">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <circle cx="8" cy="8" r="6.5" />
              <path d="M6 6.2a2 2 0 1 1 2.8 1.8c-.6.3-.8.7-.8 1.3M8 11.6v.2" strokeLinecap="round" />
            </svg>
          </button>,
          helpSlot,
        )}
      {intro && <Intro onClose={() => setIntro(false)} />}
      {hover && <Tooltip hover={hover} dims={dims} state={state} />}
      {!phone && <Panel manifest={manifest} dims={dims} state={state} onChange={update} highlight={hover ? hoverBivar(hover) : null} />}
      {hint && (
        <div className="absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded-panel border border-rule bg-panel-solid px-3 py-1.5 text-[13px] shadow-sm" role="status">
          {hint}
        </div>
      )}
      {!phone && place}
      {phone && (
        <Sheet
          snap={snap}
          onSnap={setSnap}
          tabs={[
            { id: "layers", label: "Layers" },
            { id: "place", label: selected ? "Place" : "Place (tap a hexagon)" },
          ]}
          tab={tab}
          onTab={(id) => setTab(id as "layers" | "place")}
        >
          {tab === "layers" ? (
            <Panel manifest={manifest} dims={dims} state={state} onChange={update} embedded />
          ) : (
            (place ?? <p className="py-6 text-center text-[13px] text-muted">Tap a hexagon on the map, or search for a place, to see its values here.</p>)
          )}
        </Sheet>
      )}
    </div>
  );
}
