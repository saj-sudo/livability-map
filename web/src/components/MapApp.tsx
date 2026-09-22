"use client";

// Client shell: owns the URL-backed app state (SPEC §10), the selected hex, the fly-to
// request from search, the hover readout and the panels. The map itself is loaded without
// SSR because MapLibre needs the DOM and WebGL2.

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import ComparePanel from "./ComparePanel";
import Inspector from "./Inspector";
import Panel from "./Panel";
import Search from "./Search";
import Tooltip from "./Tooltip";
import type { FlyTo, HoveredHex, SelectedHex } from "./MapView";
import type { ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { zoomFor, type Place } from "../lib/search";
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
  const urlTimer = useRef<number | null>(null);

  // read the URL once on the client after hydration (no useSearchParams: static export). The
  // server prerenders the default state, so this has to be a post-mount update.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(parseState(window.location.search));
    setReady(true);
    setSearchSlot(document.getElementById("search-slot"));
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
      }
    },
    [picking, selected],
  );
  const startPicking = useCallback(() => {
    setPicking(true);
    setHint("Click or search a second place to compare");
  }, []);

  const tilesKey = manifest.tiles?.hexes?.key ?? "hexes.pmtiles";
  const tileLayers = manifest.tiles?.hexes?.layers?.map((l) => ({ name: l.name, minzoom: l.minzoom, maxzoom: l.maxzoom }));

  return (
    <div className="map-shell">
      {ready && <MapView tilesKey={tilesKey} tileLayers={tileLayers} dims={dims} state={state} flyTo={flyTo} onMove={onMove} onSelect={onSelect} onHover={setHover} onHint={setHint} />}
      {searchSlot && createPortal(<Search onPick={onPick} className="mx-auto w-full max-w-md" />, searchSlot)}
      {hover && <Tooltip hover={hover} dims={dims} state={state} />}
      <Panel manifest={manifest} dims={dims} state={state} onChange={update} highlight={hover ? hoverBivar(hover) : null} />
      {hint && (
        <div className="absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded-panel border border-rule bg-panel-solid px-3 py-1.5 text-[13px] shadow-sm" role="status">
          {hint}
        </div>
      )}
      {selected && compare ? (
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
        />
      ) : (
        selected && <Inspector hex={selected} manifest={manifest} dims={dims} state={state} onClose={() => setSelected(null)} onCompare={startPicking} />
      )}
    </div>
  );
}
