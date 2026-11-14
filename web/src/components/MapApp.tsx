"use client";

// Client shell: owns the URL-backed app state (SPEC §10), the selected hex, the fly-to
// request from search, the hover readout and the panels. The map itself is loaded without
// SSR because MapLibre needs the DOM and WebGL2.

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ComparePanel from "./ComparePanel";
import Inspector from "./Inspector";
import { CompactLegend } from "./Legend";
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
import { describeHex } from "../lib/inspect";
import { shouldShowIntro } from "../lib/intro";
import { NO_PROBLEMS, problemMessage, supportsWebGL2, type MapProblems } from "../lib/mapHealth";
import { placeAnnouncement, placeHeader } from "../lib/place";
import { zoomFor, type Place } from "../lib/search";
import { EMPTY_SELECTION, PICK_BANNER, selectionReducer, type Selection, type SelectionAction } from "../lib/selection";
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

/** Typing in a field: Escape there belongs to the field. */
const isEditable = (t: EventTarget | null): boolean => t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));

/** Give keyboard focus back to the map after the place panel closes. */
const focusMap = () => document.querySelector<HTMLElement>(".maplibregl-canvas")?.focus({ preventScroll: true });

export default function MapApp({ manifest, dims }: Props) {
  const [state, setState] = useState<AppState>(DEFAULT_STATE);
  const [ready, setReady] = useState(false);
  // place A, place B while comparing, and whether B is being picked (session-only, not in the
  // URL); the transitions live in lib/selection.ts
  const [sel, setSel] = useState<Selection<SelectedHex>>(EMPTY_SELECTION);
  const selRef = useRef(sel);
  const [hint, setHint] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<FlyTo | null>(null);
  const [hover, setHover] = useState<HoveredHex | null>(null);
  const helpButton = useRef<HTMLButtonElement>(null);
  const introRef = useRef(false);
  const [searchSlot, setSearchSlot] = useState<HTMLElement | null>(null);
  const [helpSlot, setHelpSlot] = useState<HTMLElement | null>(null);
  const [intro, setIntro] = useState(false);
  const [webgl, setWebgl] = useState(true);
  const [problems, setProblems] = useState<MapProblems>(NO_PROBLEMS);
  // phone layout: one bottom sheet with two tabs instead of floating panels
  const phone = useMediaQuery(PHONE_QUERY);
  const [snap, setSnap] = useState<Snap>("peek");
  const [tab, setTab] = useState<"layers" | "place">("layers");
  const urlTimer = useRef<number | null>(null);
  const phoneRef = useRef(phone);
  useEffect(() => {
    phoneRef.current = phone;
    introRef.current = intro;
  });

  // read the URL once on the client after hydration (no useSearchParams: static export). The
  // server prerenders the default state, so this has to be a post-mount update.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(parseState(window.location.search));
    setReady(true);
    setSearchSlot(document.getElementById("search-slot"));
    setHelpSlot(document.getElementById("help-slot"));
    setIntro(shouldShowIntro(window.localStorage));
    setWebgl(supportsWebGL2());
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
  const onPick = useCallback((p: Place) => setFlyTo({ lat: p.lat, lng: p.lng, zoom: zoomFor(p), nonce: Date.now(), place: { name: p.name, kind: p.kind } }), []);

  // every selection change goes through the pure reducer; the panel, the sheet and the map
  // outlines all follow the one result
  const act = useCallback((action: SelectionAction<SelectedHex>) => {
    const prev = selRef.current;
    const next = selectionReducer(prev, action);
    if (next === prev) return;
    selRef.current = next;
    setSel(next);
    if ((next.a && next.a !== prev.a) || (next.b && next.b !== prev.b)) {
      setTab("place");
      setSnap((s) => (s === "peek" ? "half" : s));
    }
    // on a phone the sheet steps aside while picking so the map can be tapped
    if (next.picking && !prev.picking && phoneRef.current) setSnap("peek");
    if (!next.a && prev.a) focusMap();
  }, []);
  // a click (or a search landing) either selects, or fills the second slot while picking
  const onSelect = useCallback((hex: SelectedHex | null) => act({ type: "select", hex }), [act]);
  const startPicking = useCallback(() => act({ type: "startPicking" }), [act]);

  // Escape: cancel picking, then close the comparison, then the place panel. Not while the
  // intro is open (it has its own Escape) and not while typing, except to cancel picking when the
  // search box did not use the key itself.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || introRef.current) return;
      const s = selRef.current;
      if (!s.a) return;
      if (!s.picking && isEditable(e.target)) return;
      act({ type: "escape" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act]);

  const selected = sel.a;
  const compare = sel.b;
  const selection = useMemo(() => [sel.a, sel.b].filter((h): h is SelectedHex => h !== null), [sel.a, sel.b]);

  // what a screen reader hears when the panel switches place (the live region below)
  const announcement = useMemo(() => {
    const hex = sel.b ?? sel.a;
    if (!hex) return "";
    return placeAnnouncement(placeHeader(describeHex(hex.props, hex.sourceLayer, dims, manifest), hex.place), sel.b !== null);
  }, [sel.a, sel.b, dims, manifest]);

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
        onSwap={() => act({ type: "swap" })}
        onRepick={startPicking}
        onClose={() => act({ type: "closeCompare" })}
        embedded={phone}
      />
    ) : selected ? (
      <Inspector hex={selected} manifest={manifest} dims={dims} state={state} onClose={() => act({ type: "close" })} onCompare={startPicking} picking={sel.picking} embedded={phone} />
    ) : null;

  return (
    <div className="map-shell">
      {ready && webgl && <MapView archives={archives} tileLayers={tileLayers} dims={dims} state={state} flyTo={flyTo} selection={selection} onMove={onMove} onSelect={onSelect} onHover={setHover} onHint={setHint} onProblems={setProblems} />}
      {ready && !webgl && (
        <div className="absolute inset-0 grid place-items-center p-6">
          <div className="max-w-md rounded-panel border border-rule bg-panel-solid p-4 text-[14px] leading-relaxed" role="alert">
            <p className="font-medium">This map needs WebGL 2, and this browser has it turned off or does not support it.</p>
            <p className="mt-2 text-muted">Turning on hardware acceleration in the browser settings usually fixes it. The <a className="underline" href="/methodology/">methodology</a> and <a className="underline" href="/about/">about</a> pages work without it.</p>
          </div>
        </div>
      )}
      {searchSlot && createPortal(<Search onPick={onPick} placeholder={sel.picking ? "Search for a second place" : undefined} className="mx-auto w-full max-w-md" />, searchSlot)}
      {helpSlot &&
        createPortal(
          <button ref={helpButton} type="button" onClick={() => setIntro(true)} aria-label="How to read this map" title="How to read this map" className="grid h-8 w-8 place-items-center rounded-panel text-muted hover:bg-rule/60 hover:text-ink">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <circle cx="8" cy="8" r="6.5" />
              <path d="M6 6.2a2 2 0 1 1 2.8 1.8c-.6.3-.8.7-.8 1.3M8 11.6v.2" strokeLinecap="round" />
            </svg>
          </button>,
          helpSlot,
        )}
      {intro && (
        <Intro
          phone={phone}
          onClose={() => {
            setIntro(false);
            helpButton.current?.focus();
          }}
        />
      )}
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      {hover && <Tooltip hover={hover} dims={dims} state={state} />}
      {!phone && <Panel manifest={manifest} dims={dims} state={state} onChange={update} highlight={hover ? hoverBivar(hover) : null} />}
      {(hint || problemMessage(problems) || sel.picking) && (
        <div className="pointer-events-none absolute left-1/2 top-3 z-20 flex w-[min(28rem,calc(100%-2rem))] -translate-x-1/2 flex-col items-center gap-2">
          {sel.picking && (
            <div className="pointer-events-auto flex items-center gap-3 rounded-panel border border-accent bg-panel-solid py-1.5 pl-3 pr-1.5 text-[13px] shadow-sm" role="status" data-testid="pick-banner">
              <span>{PICK_BANNER}</span>
              <button type="button" onClick={() => act({ type: "cancelPicking" })} className="shrink-0 rounded-panel border border-rule px-2 py-0.5 text-[12px] hover:border-muted">
                Cancel
              </button>
            </div>
          )}
          {problemMessage(problems) && (
            <div className="rounded-panel border border-rule bg-panel-solid px-3 py-1.5 text-[13px] shadow-sm" role="alert">
              {problemMessage(problems)}
            </div>
          )}
          {hint && (
            <div className="rounded-panel border border-rule bg-panel-solid px-3 py-1.5 text-[13px] shadow-sm" role="status">
              {hint}
            </div>
          )}
        </div>
      )}
      {!phone && place}
      {phone && (
        <Sheet
          peek={<CompactLegend view={state.view} dims={dims} conf={state.conf} />}
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
