"use client";

// The controls (SPEC §10, §13.50): the two doors, then either the climate layers or the
// My-priorities controls (SPEC §20.5), the confidence and inhabited toggles, and scenario and
// horizon as a static line. A docked rail on a wide screen, the Layers tab of the sheet on a
// phone. One surface; hierarchy comes from type and hairlines, not nested boxes. The key is on
// the map (components/Legend.tsx), not in here.

import Doors from "./Doors";
import { useTheme } from "./useTheme";
import PrioritiesPanel from "./PrioritiesPanel";
import { SCENARIO_LABELS, type ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { paletteFor, type Palette } from "../lib/palette";
import type { AppState, ViewId } from "../lib/url";

/** The layers behind the "Climate in 2050" door, in list order. */
export const CLIMATE_VIEWS: readonly ViewId[] = ["exp", "heat", "humid", "rflood", "cflood", "wstress"];
/** One step in: wellbeing beside exposure, or on its own. */
export const WELLBEING_VIEWS: readonly ViewId[] = ["bivar", "wb"];

export const VIEW_LABELS: Record<ViewId, string> = {
  exp: "All five hazards together",
  heat: "Extreme heat",
  humid: "Humid heat",
  rflood: "Riverine flood",
  cflood: "Coastal flood",
  wstress: "Water stress",
  bivar: "Add wellbeing beside exposure",
  wb: "Wellbeing today alone",
  priorities: "My priorities",
};

interface Props {
  manifest: ClientManifest;
  dims: DimInfo[];
  state: AppState;
  onChange: (patch: Partial<AppState>) => void;
  onDoor: (view: ViewId) => void;
  onShare?: () => void;
  /** rendered inside the phone bottom sheet: no rail chrome */
  embedded?: boolean;
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
  const ramp = view === "wb" ? pal.rampWellbeing : pal.rampHazard;
  return <span className="h-3 w-3 shrink-0 rounded-[2px]" style={{ background: `linear-gradient(135deg, ${ramp[0]}, ${ramp[2]})` }} aria-hidden="true" />;
}

export function Toggle({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: React.ReactNode }) {
  return (
    <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-small sm:min-h-0">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-6 w-6 shrink-0 accent-accent" />
      <span>{children}</span>
    </label>
  );
}

function ViewList({ views, state, pal, onChange }: { views: readonly ViewId[]; state: AppState; pal: Palette; onChange: (patch: Partial<AppState>) => void }) {
  return (
    <div className="-mx-1 space-y-px">
      {views.map((v) => {
        const active = state.view === v;
        return (
          <label key={v} className={`flex min-h-[44px] cursor-pointer items-center gap-2 rounded-[4px] px-2 text-small has-focus-visible:outline-2 has-focus-visible:outline-accent sm:min-h-[30px] ${active ? "bg-rule/70 font-medium" : "hover:bg-rule/40"}`}>
            <input type="radio" name="view" value={v} checked={active} onChange={() => onChange({ view: v })} className="sr-only" />
            <ViewKey view={v} pal={pal} />
            <span>{VIEW_LABELS[v]}</span>
          </label>
        );
      })}
    </div>
  );
}

export default function Panel({ manifest, dims, state, onChange, onDoor, onShare, embedded }: Props) {
  const [theme] = useTheme();
  const pal = paletteFor(theme);
  return (
    <div className={embedded ? "space-y-3" : "flex h-full flex-col gap-3 overflow-auto p-3"}>
      <Doors view={state.view} onDoor={onDoor} />

      {state.view === "priorities" ? (
        <PrioritiesPanel dims={dims} state={state} onChange={onChange} onShare={onShare} />
      ) : (
        <fieldset className="space-y-2">
          <legend className="sr-only">Map layer</legend>
          <ViewList views={CLIMATE_VIEWS} state={state} pal={pal} onChange={onChange} />
          <div className="border-t border-rule pt-2 font-serif text-[14px] text-muted">With wellbeing</div>
          <ViewList views={WELLBEING_VIEWS} state={state} pal={pal} onChange={onChange} />
        </fieldset>
      )}

      <div className="space-y-1.5 border-t border-rule pt-2">
        <Toggle checked={state.conf} onChange={(v) => onChange({ conf: v })}>
          Mark places missing some hazard data
        </Toggle>
        <Toggle checked={state.inh} onChange={(v) => onChange({ inh: v })}>
          Show places where almost no one lives (under 100 people)
        </Toggle>
      </div>

      <p className={`border-t border-rule pt-2 font-serif text-small italic text-muted ${embedded ? "" : "mt-auto"}`}>
        Hazards are projections for {manifest.horizon} under a {SCENARIO_LABELS[manifest.scenario] ?? manifest.scenario}; wellbeing and life dimensions are present-day.
      </p>
      {manifest.fixtures && <p className="text-fine text-muted">Synthetic fixture data, not the real world.</p>}
      {embedded && (
        <p className="border-t border-rule pt-2 text-fine text-muted">
          <a href="/methodology/" className="underline decoration-rule underline-offset-2 hover:text-ink">
            Methodology
          </a>
          {" and "}
          <a href="/about/" className="underline decoration-rule underline-offset-2 hover:text-ink">
            About
          </a>
          , including what this map does not do.
        </p>
      )}
    </div>
  );
}
