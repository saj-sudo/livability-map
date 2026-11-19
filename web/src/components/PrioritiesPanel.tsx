"use client";

// My-priorities controls (SPEC §20.5, decisions §13.15, §13.50): presets first, as cards, then a
// 0-5 slider per dimension with its coverage chip and a numeric readout, folded by group, and the pick for the signed (political
// lean) dimension. Composition dimensions get no slider: they are context in the place panel,
// never a priority (§13.40). Moving a slider clears the preset; picking a preset replaces the
// weights. Dimensions are grouped by the manifest's `group`, so a new dimension lands in the
// right place with no code change.

import type { DimGroup } from "../lib/manifest";
import { shortName, weightable, type DimInfo } from "../lib/dims";
import { DEFAULT_STATE, MAX_WEIGHT, type AppState } from "../lib/url";
import { PRESETS, presetById, type PolPick } from "../presets";

interface Props {
  dims: DimInfo[];
  state: AppState;
  onChange: (patch: Partial<AppState>) => void;
  onShare?: () => void;
}

const POL_OPTIONS: { id: PolPick; label: string }[] = [
  { id: "left", label: "leans Democratic" },
  { id: "competitive", label: "competitive" },
  { id: "right", label: "leans Republican" },
];

const GROUP_ORDER: DimGroup[] = ["hazard", "wellbeing", "env", "life"];
const GROUP_LABELS: Record<string, string> = { hazard: "Climate hazards, 2050", wellbeing: "Wellbeing", env: "Environment today", life: "Work, home and community" };

function groupsOf(dims: DimInfo[]): { group: string; label: string; dims: DimInfo[] }[] {
  const seen = new Map<string, DimInfo[]>();
  for (const d of dims) seen.set(d.group, [...(seen.get(d.group) ?? []), d]);
  const order = [...GROUP_ORDER, ...[...seen.keys()].filter((g) => !(GROUP_ORDER as string[]).includes(g))];
  return order.filter((g) => seen.has(g)).map((g) => ({ group: g, label: GROUP_LABELS[g] ?? g.charAt(0).toUpperCase() + g.slice(1), dims: seen.get(g)! }));
}

const selectCls = "mt-0.5 w-full rounded-[4px] border border-rule bg-panel-solid px-1.5 py-1 text-small text-ink";

export default function PrioritiesPanel({ dims, state, onChange, onShare }: Props) {
  const setWeight = (id: string, w: number) => {
    const weights = { ...state.weights };
    if (w > 0) weights[id] = w;
    else delete weights[id];
    onChange({ weights, preset: null });
  };
  const applyPreset = (id: string) => {
    const p = presetById(id);
    if (!p) return;
    onChange({ preset: p.id, weights: { ...p.weights }, pol: p.pol ?? state.pol });
  };
  const active = presetById(state.preset);
  const weighted = Object.values(state.weights).some((w) => w > 0);
  const contextOnly = dims.filter((d) => !weightable(d));
  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1.5 font-serif text-[14px] text-muted">Start from</div>
        <div className="grid grid-cols-2 gap-1.5" role="group" aria-label="Presets">
          {PRESETS.map((p) => {
            const on = state.preset === p.id;
            return (
              <button key={p.id} type="button" onClick={() => applyPreset(p.id)} aria-pressed={on} className={`min-h-[44px] rounded-panel border px-2 py-1.5 text-left text-small leading-tight ${on ? "border-ink font-semibold shadow-[inset_0_0_0_1px_var(--ink)]" : "border-rule hover:border-muted"}`}>
                {p.name}
              </button>
            );
          })}
          <button type="button" onClick={() => onChange({ weights: {}, preset: null, pol: DEFAULT_STATE.pol })} aria-pressed={!weighted && !state.preset} className={`min-h-[44px] rounded-panel border px-2 py-1.5 text-left text-small leading-tight ${!weighted && !state.preset ? "border-ink font-semibold shadow-[inset_0_0_0_1px_var(--ink)]" : "border-rule hover:border-muted"}`}>
            Start from scratch
          </button>
        </div>
        <p className="mt-1.5 min-h-[1.2em] text-fine text-muted">{active ? `Weighs ${active.blurb}.` : weighted ? "Your own weights." : "Nothing is weighted yet: open a group below and move a slider, or pick a starting point."}</p>
      </div>

      <div>
        {groupsOf(dims.filter(weightable)).map((g) => {
          const n = g.dims.filter((d) => (state.weights[d.id] ?? 0) > 0).length;
          return (
            <details key={g.group} className="border-t border-rule">
              <summary className="flex min-h-[44px] cursor-pointer items-center justify-between gap-2 text-small">
                <span>{g.label}</span>
                <span className="text-fine text-muted">
                  {n ? `${n} weighted` : "none"} <span aria-hidden="true">›</span>
                </span>
              </summary>
              {g.group === "hazard" && <p className="mb-1 text-fine text-muted">Less is better for all of these.</p>}
              <ul className="space-y-1 pb-2">
                {g.dims.map((d) => {
                  const w = state.weights[d.id] ?? 0;
                  return (
                    <li key={d.id} className="grid grid-cols-[1fr_5rem_1rem] items-center gap-x-2">
                      <label htmlFor={`w-${d.id}`} className="min-w-0 leading-tight">
                        <span className={`block truncate text-small ${d.available ? "" : "text-muted"}`} title={d.name}>
                          {shortName(d.name)}
                        </span>
                        <span className="block text-fine text-muted">
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
                        className="h-[44px] w-full accent-accent disabled:opacity-40 sm:h-6"
                        aria-label={`weight for ${d.name}`}
                        aria-valuetext={w === 0 ? "off" : `${w} of ${MAX_WEIGHT}`}
                      />
                      <span className={`text-right text-small tabular-nums ${w ? "text-ink" : "text-muted"}`} aria-hidden="true">
                        {w || "–"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </details>
          );
        })}
      </div>

      {(state.weights.pol ?? 0) > 0 && (
        <label className="block text-fine text-muted">
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
      {contextOnly.length > 0 && (
        <p className="text-fine text-muted">
          {contextOnly.map((d) => shortName(d.name)).join(", ")} {contextOnly.length > 1 ? "are" : "is"} shown for each place as context, not offered as a priority: ranking places by who lives there is steering, and this map does not do it.
        </p>
      )}
      <p className="text-fine text-muted">A layer with no data for a place drops out of that place&rsquo;s average; places with none of your weighted layers stay grey.</p>
      {onShare && (
        <button type="button" onClick={onShare} disabled={!weighted} className="flex min-h-[44px] w-full items-center justify-between rounded-panel border border-rule px-3 text-small hover:border-muted disabled:text-muted">
          Share this map <span aria-hidden="true">›</span>
        </button>
      )}
    </div>
  );
}
