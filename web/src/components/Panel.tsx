"use client";

// Left panel (SPEC §10): view selector, the My-priorities controls (SPEC §20.5), scenario line,
// confidence and inhabited toggles, and the legend (SPEC §9.3). One surface; hierarchy comes
// from type and hairlines, not nested boxes.

import { useEffect, useState } from "react";
import { useTheme } from "./useTheme";
import Legend from "./Legend";
import PrioritiesPanel from "./PrioritiesPanel";
import { SCENARIO_LABELS, type ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { paletteFor, type Palette } from "../lib/palette";
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
  /** bivariate class of the hovered hex, passed through to the legend */
  highlight?: number | null;
}

/** A 12px key showing what colours the view uses. */
function ViewKey({ view, pal }: { view: ViewId; pal: Palette }) {
  if (view === "bivar") {
    return (
      <span className="grid h-3 w-3 shrink-0 grid-cols-2 gap-px" aria-hidden="true">
        <i style={{ background: pal.bivar[7] }} />
        <i style={{ background: pal.bivar[9] }} />
        <i style={{ background: pal.bivar[1] }} />
        <i style={{ background: pal.bivar[3] }} />
      </span>
    );
  }
  const ramp = view === "priorities" ? pal.rampPriority : view === "wb" ? pal.rampWellbeing : pal.rampHazard;
  return <span className="h-3 w-3 shrink-0 rounded-[2px]" style={{ background: `linear-gradient(135deg, ${ramp[0]}, ${ramp[2]})` }} aria-hidden="true" />;
}

export function Toggle({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-[13px]">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-[3px] h-3.5 w-3.5 shrink-0 accent-accent" />
      <span>{children}</span>
    </label>
  );
}

export default function Panel({ manifest, dims, state, onChange, highlight }: Props) {
  const [open, setOpen] = useState(true);
  const [theme] = useTheme();
  const pal = paletteFor(theme);
  // on a phone the panel would cover the whole map, so start collapsed there (after hydration,
  // because the server render cannot know the viewport)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (window.matchMedia("(max-width: 640px)").matches) setOpen(false);
  }, []);
  return (
    <aside className="absolute left-3 top-3 z-10 max-h-[calc(100%-1.5rem)] w-[19rem] max-w-[calc(100%-1.5rem)] overflow-auto rounded-panel border border-rule bg-panel shadow-[0_1px_2px_rgba(0,0,0,.06),0_8px_24px_-12px_rgba(0,0,0,.25)] backdrop-blur-sm">
      <button type="button" className="flex w-full items-center justify-between px-3 py-2 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="font-serif text-[16px]">Layers</span>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" className={`text-muted transition-transform ${open ? "" : "-rotate-90"}`}>
          <path d="M3 5l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>
      {open && (
        <div className="space-y-3 px-3 pb-3">
          <fieldset>
            <legend className="sr-only">Map view</legend>
            <div className="-mx-1 space-y-px">
              {VIEWS.map((v) => {
                const active = state.view === v;
                return (
                  <label key={v} className={`flex cursor-pointer items-center gap-2 rounded-[4px] px-2 py-[5px] text-[13px] has-focus-visible:outline-2 has-focus-visible:outline-accent ${active ? "bg-rule/70 font-medium" : "hover:bg-rule/40"}`}>
                    <input type="radio" name="view" value={v} checked={active} onChange={() => onChange({ view: v })} className="sr-only" />
                    <ViewKey view={v} pal={pal} />
                    <span>{VIEW_LABELS[v]}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {state.view === "priorities" && <PrioritiesPanel dims={dims} state={state} onChange={onChange} />}

          <p className="border-t border-rule pt-2 font-serif text-[13px] italic text-muted">
            Hazards are projections for {manifest.horizon} under a {SCENARIO_LABELS[manifest.scenario] ?? manifest.scenario}; wellbeing and life dimensions are present-day.
          </p>

          <div className="space-y-1.5">
            <Toggle checked={state.conf} onChange={(v) => onChange({ conf: v })}>
              Hatch hexes with fewer than 4 hazard layers
            </Toggle>
            <Toggle checked={state.inh} onChange={(v) => onChange({ inh: v })}>
              Show uninhabited hexes (under 100 people)
            </Toggle>
          </div>

          <div className="border-t border-rule pt-2">
            <Legend view={state.view} dims={dims} conf={state.conf} theme={theme} highlight={highlight} />
          </div>
          {manifest.fixtures && <p className="text-[12px] text-muted">Synthetic fixture data, not the real world.</p>}
        </div>
      )}
    </aside>
  );
}
