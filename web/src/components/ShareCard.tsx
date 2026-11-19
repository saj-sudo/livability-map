"use client";

// The card a "Share this map" link opens with (SPEC §10, §13.50): whose weights these are, what
// they were, the key, the year and pathway, and where the data comes from. It never lists places.

import { useEffect, useRef } from "react";
import { CompactLegend } from "./Legend";
import type { ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { pathwayLabel } from "../lib/plate";
import { shareTitle, sourcesLine, weightsInWords } from "../lib/share";
import type { AppState } from "../lib/url";

interface Props {
  manifest: ClientManifest;
  dims: DimInfo[];
  state: AppState;
  onClose: () => void;
}

export default function ShareCard({ manifest, dims, state, onClose }: Props) {
  const go = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    go.current?.focus();
  }, []);
  return (
    <div role="dialog" aria-labelledby="share-title" className="absolute left-1/2 top-1/2 z-30 flex max-h-[calc(100%-1.5rem)] w-[26rem] max-w-[calc(100%-1.5rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 overflow-auto rounded-panel border border-rule bg-panel-solid p-5" data-testid="share-card">
      <h2 id="share-title" className="font-serif text-[26px] leading-[1.1]">
        {shareTitle(state.preset)}
      </h2>
      <p className="text-small leading-snug">
        <span className="text-muted">What was weighted: </span>
        {weightsInWords(dims, state.weights)}
      </p>
      <CompactLegend view="priorities" dims={dims} conf={false} />
      <p className="font-serif text-small italic leading-snug text-muted">
        Hazards: {manifest.horizon}, {pathwayLabel(manifest).replace(/^./, (c) => c.toLowerCase())}. {sourcesLine(manifest.sources)} One person&rsquo;s priorities, not a ranking of places.
      </p>
      <button ref={go} type="button" onClick={onClose} className="flex min-h-[44px] items-center justify-center rounded-panel bg-ink px-3 text-small font-semibold text-panel-solid">
        Look at this map
      </button>
    </div>
  );
}
