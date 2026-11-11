"use client";

// Two places side by side (SPEC §10 v2). Replaces the inspector while a second hex is set.
// A small accent mark shows which side is better on rows where that has a meaning and both
// sides have data; "no data here" stays visible, never a zero.

import { useMemo } from "react";
import type { SelectedHex } from "./MapView";
import type { ClientManifest } from "../lib/clientManifest";
import { compareRows, type RowGroup } from "../lib/compare";
import { shortName, type DimInfo } from "../lib/dims";
import { describeHex } from "../lib/inspect";
import type { AppState } from "../lib/url";

interface Props {
  a: SelectedHex;
  b: SelectedHex;
  manifest: ClientManifest;
  dims: DimInfo[];
  state: AppState;
  onSwap: () => void;
  onRepick: () => void;
  onClose: () => void;
  embedded?: boolean;
}

const GROUP_TITLES: Record<RowGroup, string> = { summary: "", priorities: "Your priorities", hazard: "Climate hazards", wellbeing: "Wellbeing", life: "Life dimensions" };
const GROUPS: RowGroup[] = ["summary", "priorities", "hazard", "wellbeing", "life"];

export default function ComparePanel({ a, b, manifest, dims, state, onSwap, onRepick, onClose, embedded }: Props) {
  const picks = useMemo(() => ({ pol: state.pol }), [state.pol]);
  const ma = useMemo(() => describeHex(a.props, a.sourceLayer, dims, manifest), [a, dims, manifest]);
  const mb = useMemo(() => describeHex(b.props, b.sourceLayer, dims, manifest), [b, dims, manifest]);
  const rows = useMemo(() => compareRows({ model: ma, props: a.props }, { model: mb, props: b.props }, dims, state.weights, picks), [ma, mb, a.props, b.props, dims, state.weights, picks]);

  const Cell = ({ value, lean }: { value: string | null; lean: boolean }) => (
    <td className={`py-[3px] pr-2 align-top text-[12px] ${value === null ? "text-muted" : ""}`}>
      {lean && <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-accent align-middle" aria-label="better on this row" />}
      {value ?? "no data here"}
    </td>
  );

  return (
    <section className={embedded ? "text-[13px]" : "absolute bottom-3 right-3 z-10 max-h-[calc(100%-1.5rem)] w-[30rem] max-w-[calc(100%-1.5rem)] overflow-auto rounded-panel border border-rule bg-panel p-3 text-[13px] shadow-[0_1px_2px_rgba(0,0,0,.06),0_8px_24px_-12px_rgba(0,0,0,.25)] backdrop-blur-sm"} aria-label="Compare two places">
      <div className="flex items-start justify-between gap-2">
        <h2 className="font-serif text-[16px]">Side by side</h2>
        <div className="flex gap-1">
          <button type="button" onClick={onSwap} className="rounded-panel px-2 py-0.5 text-[12px] text-muted hover:bg-rule hover:text-ink">
            Swap
          </button>
          <button type="button" onClick={onRepick} className="rounded-panel px-2 py-0.5 text-[12px] text-muted hover:bg-rule hover:text-ink">
            Change second place
          </button>
          <button type="button" onClick={onClose} className="grid h-7 w-7 place-items-center rounded-panel text-muted hover:bg-rule hover:text-ink" aria-label="Close comparison">
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
        </div>
      </div>
      <table className="mt-2 w-full table-fixed border-collapse">
        <thead>
          <tr className="text-left align-top">
            <th className="w-[30%] pb-1 pr-2 font-normal text-[11px] text-muted"></th>
            <th className="pb-1 pr-2 font-serif text-[15px] font-normal leading-tight">
              {ma.title}
              <div className="font-sans text-[11px] text-muted">{ma.subtitle}</div>
            </th>
            <th className="pb-1 font-serif text-[15px] font-normal leading-tight">
              {mb.title}
              <div className="font-sans text-[11px] text-muted">{mb.subtitle}</div>
            </th>
          </tr>
        </thead>
        <tbody>
          {GROUPS.map((g) => {
            const inGroup = rows.filter((r) => r.group === g);
            if (!inGroup.length) return null;
            return [
              GROUP_TITLES[g] ? (
                <tr key={`${g}-title`}>
                  <td colSpan={3} className="border-t border-rule pt-2 font-serif text-[13px]">
                    {GROUP_TITLES[g]}
                  </td>
                </tr>
              ) : null,
              ...inGroup.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="py-[3px] pr-2 text-[12px] text-muted" title={r.label}>
                    {shortName(r.label)}
                  </td>
                  <Cell value={r.a} lean={r.leans === "a"} />
                  <Cell value={r.b} lean={r.leans === "b"} />
                </tr>
              )),
            ];
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-muted">A dot marks the side that does better on a row; rows with a side missing are not judged.</p>
    </section>
  );
}
