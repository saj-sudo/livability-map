"use client";

// My-priorities controls (SPEC §20.5, decision §13.15): presets, a 0-5 slider per dimension
// with its coverage chip, and the picks for the signed (political lean) and composition
// (racial composition) dimensions. Moving a slider clears the preset; picking a preset
// replaces the weights. Everything recolours client-side.

import { lifeDims, type DimInfo } from "../lib/dims";
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

export default function PrioritiesPanel({ dims, state, onChange }: Props) {
  const ordered = [...dims.filter((d) => d.group !== "life"), ...lifeDims(dims)];
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
  return (
    <div className="space-y-2 rounded border border-[var(--border)] bg-white p-2">
      <label className="block text-xs text-[var(--muted)]">
        Preset
        <select className="mt-0.5 w-full rounded border border-[var(--border)] px-1 py-0.5 text-sm" value={state.preset ?? ""} onChange={(e) => (e.target.value ? applyPreset(e.target.value) : onChange({ preset: null }))}>
          <option value="">custom</option>
          {PRESETS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {state.preset && <p className="text-xs text-[var(--muted)]">{presetById(state.preset)?.blurb}</p>}
      <ul className="space-y-1">
        {ordered.map((d) => (
          <li key={d.id} className="grid grid-cols-[1fr_auto] items-center gap-2">
            <label htmlFor={`w-${d.id}`} className="flex flex-col leading-tight">
              <span>
                {d.name}
                {d.higher_is === "worse" && d.group !== "hazard" && <span className="text-[var(--muted)]"> (less is better)</span>}
                {d.group === "hazard" && <span className="text-[var(--muted)]"> (less is better)</span>}
              </span>
              {d.chip && <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{d.chip}</span>}
            </label>
            <input id={`w-${d.id}`} type="range" min={0} max={MAX_WEIGHT} step={1} value={state.weights[d.id] ?? 0} onChange={(e) => setWeight(d.id, Number(e.target.value))} className="w-24" aria-label={`weight for ${d.name}`} />
          </li>
        ))}
      </ul>
      {(state.weights.pol ?? 0) > 0 && (
        <label className="block text-xs">
          Political lean I want
          <select className="mt-0.5 w-full rounded border border-[var(--border)] px-1 py-0.5 text-sm" value={state.pol} onChange={(e) => onChange({ pol: e.target.value as PolPick })}>
            {POL_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {(state.weights.race ?? 0) > 0 && (
        <label className="block text-xs">
          Composition I want
          <select className="mt-0.5 w-full rounded border border-[var(--border)] px-1 py-0.5 text-sm" value={state.race} onChange={(e) => onChange({ race: e.target.value as RacePick })}>
            {RACE_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="text-xs text-[var(--muted)]">Dimensions missing on a hex drop out of its average; hexes with none of your weighted dimensions are grey.</p>
    </div>
  );
}
