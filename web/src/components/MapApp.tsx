"use client";

// Client shell: owns the URL-backed app state (SPEC §10), the selected hex and the panels.
// The map itself is loaded without SSR because MapLibre needs the DOM and WebGL2.

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import Inspector from "./Inspector";
import Panel from "./Panel";
import type { SelectedHex } from "./MapView";
import type { ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { DEFAULT_STATE, parseState, writeUrl, type AppState } from "../lib/url";

const MapView = dynamic(() => import("./MapView"), { ssr: false, loading: () => <div className="absolute inset-0 grid place-items-center text-[var(--muted)]">Loading map…</div> });

interface Props {
  manifest: ClientManifest;
  dims: DimInfo[];
}

export default function MapApp({ manifest, dims }: Props) {
  const [state, setState] = useState<AppState>(DEFAULT_STATE);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<SelectedHex | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const urlTimer = useRef<number | null>(null);

  // read the URL once on the client after hydration (no useSearchParams: static export). The
  // server prerenders the default state, so this has to be a post-mount update.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(parseState(window.location.search));
    setReady(true);
  }, []);

  // write the URL on every state change, debounced so map moves do not thrash history
  useEffect(() => {
    if (!ready) return;
    if (urlTimer.current) window.clearTimeout(urlTimer.current);
    urlTimer.current = window.setTimeout(() => writeUrl(state), 150);
  }, [state, ready]);

  const onMove = useCallback((lat: number, lng: number, z: number) => setState((s) => ({ ...s, lat, lng, z })), []);
  const update = useCallback((patch: Partial<AppState>) => setState((s) => ({ ...s, ...patch })), []);

  const tilesKey = manifest.tiles?.hexes?.key ?? "hexes.pmtiles";

  return (
    <div className="map-shell">
      {ready && <MapView tilesKey={tilesKey} dims={dims} state={state} onMove={onMove} onSelect={setSelected} onHint={setHint} />}
      <Panel manifest={manifest} dims={dims} state={state} onChange={update} />
      {hint && (
        <div className="absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded bg-white/95 px-3 py-1.5 text-sm shadow" role="status">
          {hint}
        </div>
      )}
      {selected && <Inspector hex={selected} manifest={manifest} dims={dims} onClose={() => setSelected(null)} />}
    </div>
  );
}
