"use client";

// My-priorities controls (SPEC §20.5, decision §13.15): presets as chips, a 0-5 slider per
// dimension with its coverage chip and a numeric readout, and the picks for the signed
// (political lean) and composition (racial composition) dimensions. Moving a slider clears the
// preset; picking a preset replaces the weights. Dimensions are grouped by the manifest's
// `group`, so a new dimension lands in the right place with no code change.

import type { DimGroup } from "../lib/manifest";
import { shortName, type DimInfo } from "../lib/dims";
import { MAX_WEIGHT, type AppState } from "../lib/url";
import { PRESETS, presetById, type PolPick, type RacePick } from "../presets";

interface Props {
  dims: DimInfo[];
  state: AppState;
  onChange: (patch: Partial<AppState>) => void;
}

const POL_OPTIONS: { id: PolPick; label: string }[] = [
  { id: "left", label: "leans Democratic" },
  { id: "competitive", label: "competitive" },
  { id: "right", label: "leans Republican" },
];
const RACE_OPTIONS: { id: RacePick; label: string }[] = [
  { id: "diverse", label: "diverse (no single majority)" },
  { id: "w", label: "majority white" },
  { id: "b", label: "majority Black" },
  { id: "h", label: "majority Hispanic or Latino" },
  { id: "a", label: "majority Asian / Pacific Islander" },
  { id: "o", label: "majority other" },
];

const GROUP_ORDER: DimGroup[] = ["hazard", "wellbeing", "life"];
const GROUP_LABELS: Record<string, string> = { hazard: "Climate hazards", wellbeing: "Wellbeing", life: "Life" };

function groupsOf(dims: DimInfo[]): { group: string; label: string; dims: DimInfo[] }[] {
  const seen = new Map<string, DimInfo[]>();
  for (const d of dims) seen.set(d.group, [...(seen.get(d.group) ?? []), d]);
  const order = [...GROUP_ORDER, ...[...seen.keys()].filter((g) => !(GROUP_ORDER as string[]).includes(g))];
  return order.filter((g) => seen.has(g)).map((g) => ({ group: g, label: GROUP_LABELS[g] ?? g.charAt(0).toUpperCase() + g.slice(1), dims: seen.get(g)! }));
}

const selectCls = "mt-0.5 w-full rounded-[4px] border border-rule bg-panel-solid px-1.5 py-1 text-[13px] text-ink";

export default function PrioritiesPanel({ dims, state, onChange }: Props) {
  const setWeight = (id: string, w: number) => {
    const weights = { ...state.weights };
    if (w > 0) weights[id] = w;
    else delete weights[id];
    onChange({ weights, preset: null });
  };
  const applyPreset = (id: string) => {
    const p = presetById(id);
    if (!p) return;
    onChange({ preset: p.id, weights: { ...p.weights }, pol: p.pol ?? state.pol, race: p.race ?? state.race });
  };
  const active = presetById(state.preset);
  return (
    <div className="space-y-3 border-t border-rule pt-2">
      <div>
        <div className="mb-1 text-[12px] text-muted">Start from a preset, then adjust</div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Presets">
          {PRESETS.map((p) => {
            const on = state.preset === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => applyPreset(p.id)}
                aria-pressed={on}
                className={`rounded-full border px-2 py-[3px] text-[12px] leading-tight ${on ? "border-accent bg-accent text-accent-ink" : "border-rule bg-panel-solid text-ink hover:border-muted"}`}
              >
                {p.name}
              </button>
            );
          })}
        </div>
        <p className="mt-1 min-h-[1.2em] text-[12px] text-muted">{active ? active.blurb : Object.keys(state.weights).length ? "custom weights" : "no weights yet: move a slider or pick a preset"}</p>
      </div>

      {groupsOf(dims).map((g) => (
        <div key={g.group}>
          <div className="mb-1 flex items-baseline justify-between text-[12px] text-muted">
            <span>{g.label}</span>
            {g.group === "hazard" && <span>less is better</span>}
          </div>
          <ul className="space-y-1">
            {g.dims.map((d) => {
              const w = state.weights[d.id] ?? 0;
              return (
                <li key={d.id} className="grid grid-cols-[1fr_5rem_1rem] items-center gap-x-2">
                  <label htmlFor={`w-${d.id}`} className="min-w-0 leading-tight">
                    <span className={`block truncate text-[13px] ${d.available ? "" : "text-muted"}`} title={d.name}>
                      {shortName(d.name)}
                    </span>
                    <span className="block text-[11px] text-muted">
                      {d.available ? (
                        <>
                          {d.chip}
                          {d.higher_is === "worse" && d.group !== "hazard" && (d.chip ? " · less is better" : "less is better")}
                        </>
                      ) : (
                        "no data in this build"
                      )}
                    </span>
                  </label>
                  <input
                    id={`w-${d.id}`}
                    type="range"
                    min={0}
                    max={MAX_WEIGHT}
                    step={1}
                    value={w}
                    disabled={!d.available}
                    onChange={(e) => setWeight(d.id, Number(e.target.value))}
                    className="h-6 w-full accent-accent disabled:opacity-40"
                    aria-label={`weight for ${d.name}`}
                    aria-valuetext={w === 0 ? "off" : `${w} of ${MAX_WEIGHT}`}
                  />
                  <span className={`text-right text-[13px] tabular-nums ${w ? "text-ink" : "text-muted"}`} aria-hidden="true">
                    {w || "–"}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ))}

      {(state.weights.pol ?? 0) > 0 && (
        <label className="block text-[12px] text-muted">
          Political lean I want
          <select className={selectCls} value={state.pol} onChange={(e) => onChange({ pol: e.target.value as PolPick })}>
            {POL_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {(state.weights.race ?? 0) > 0 && (
        <label className="block text-[12px] text-muted">
          Composition I want
          <select className={selectCls} value={state.race} onChange={(e) => onChange({ race: e.target.value as RacePick })}>
            {RACE_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="text-[11px] text-muted">A dimension missing on a hex drops out of that hex&rsquo;s average; hexes with none of your weighted dimensions stay grey.</p>
    </div>
  );
}
