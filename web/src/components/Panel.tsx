"use client";

// Left panel (SPEC §10): view selector, scenario label, confidence and inhabited toggles,
// the My-priorities controls (SPEC §20.5) and the legend (SPEC §9.3).

import { useEffect, useState } from "react";
import Legend from "./Legend";
import PrioritiesPanel from "./PrioritiesPanel";
import { SCENARIO_LABELS, type ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { VIEWS, type AppState, type ViewId } from "../lib/url";

const VIEW_LABELS: Record<ViewId, string> = {
  bivar: "Climate exposure × wellbeing",
  heat: "Extreme heat",
  rflood: "Riverine flood",
  cflood: "Coastal flood",
  wstress: "Water stress",
  wb: "Wellbeing",
  priorities: "My priorities",
};

interface Props {
  manifest: ClientManifest;
  dims: DimInfo[];
  state: AppState;
  onChange: (patch: Partial<AppState>) => void;
}

export default function Panel({ manifest, dims, state, onChange }: Props) {
  const [open, setOpen] = useState(true);
  // on a phone the panel would cover the whole map, so start collapsed there (after hydration,
  // because the server render cannot know the viewport)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (window.matchMedia("(max-width: 640px)").matches) setOpen(false);
  }, []);
  return (
    <aside className="absolute left-3 top-3 z-10 max-h-[calc(100%-1.5rem)] w-[19rem] max-w-[calc(100%-1.5rem)] overflow-auto rounded-lg border border-[var(--border)] bg-[var(--panel)] text-sm shadow-md">
      <button type="button" className="flex w-full items-center justify-between px-3 py-2 text-left font-semibold" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>View</span>
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-3 px-3 pb-3">
          <fieldset className="space-y-1">
            <legend className="sr-only">Map view</legend>
            {VIEWS.map((v) => (
              <label key={v} className="flex cursor-pointer items-center gap-2">
                <input type="radio" name="view" value={v} checked={state.view === v} onChange={() => onChange({ view: v })} />
                <span>{VIEW_LABELS[v]}</span>
              </label>
            ))}
          </fieldset>

          {state.view === "priorities" && <PrioritiesPanel dims={dims} state={state} onChange={onChange} />}

          <p className="text-xs text-[var(--muted)]">
            Scenario: {SCENARIO_LABELS[manifest.scenario] ?? manifest.scenario}, horizon {manifest.horizon}. Hazards are projections; wellbeing and life dimensions are present-day.
          </p>

          <div className="space-y-1">
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" checked={state.conf} onChange={(e) => onChange({ conf: e.target.checked })} />
              <span>Hatch hexes with fewer than 4 hazard layers</span>
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" checked={state.inh} onChange={(e) => onChange({ inh: e.target.checked })} />
              <span>Show uninhabited hexes (under 100 people)</span>
            </label>
          </div>

          <Legend view={state.view} dims={dims} conf={state.conf} />
          {manifest.fixtures && <p className="text-xs text-amber-700">Synthetic fixture data, not the real world.</p>}
        </div>
      )}
    </aside>
  );
}
