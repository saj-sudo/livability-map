// Side-by-side rows for two hexes (SPEC §10, "compare two places", v2). Every row carries a
// value per side or null for "no data here", and `leans` names the side that is better for
// that row only when both sides have data (invariant 3: a missing side never loses).

import { compositeValue, type Props } from "./chart";
import type { DimInfo } from "./dims";
import type { Picks, Weights } from "./expressions";
import { formatScore } from "./format";
import type { HexModel } from "./inspect";

export interface Side {
  model: HexModel;
  props: Props;
}

export type RowGroup = "summary" | "priorities" | "hazard" | "wellbeing" | "life";

export interface CompareRow {
  id: string;
  group: RowGroup;
  label: string;
  a: string | null;
  b: string | null;
  /** the side that is better on this row, or null when not comparable */
  leans: "a" | "b" | null;
}

function lean(a: number | null, b: number | null, higherIsBetter: boolean): "a" | "b" | null {
  if (a === null || b === null || a === b) return null;
  return (a > b) === higherIsBetter ? "a" : "b";
}

const withScore = (value: string | null, score: number | null): string | null => (value === null && score === null ? null : [value, score === null ? null : formatScore(score)].filter(Boolean).join(", "));

export function compareRows(a: Side, b: Side, dims: DimInfo[], weights: Weights, picks: Picks): CompareRow[] {
  const rows: CompareRow[] = [];
  rows.push({ id: "bivar", group: "summary", label: "Combined", a: a.model.bivarClass ? a.model.bivar : null, b: b.model.bivarClass ? b.model.bivar : null, leans: null });
  rows.push({ id: "coverage", group: "summary", label: "Hazard layers present", a: `${a.model.coverageN} of 4`, b: `${b.model.coverageN} of 4`, leans: lean(a.model.coverageN, b.model.coverageN, true) });

  if (Object.values(weights).some((w) => w > 0)) {
    const ca = compositeValue(dims, weights, picks, a.props);
    const cb = compositeValue(dims, weights, picks, b.props);
    rows.push({ id: "match", group: "priorities", label: "Match with your priorities", a: ca === null ? null : formatScore(ca), b: cb === null ? null : formatScore(cb), leans: lean(ca, cb, true) });
  }

  for (const [i, ha] of a.model.hazards.entries()) {
    const hb = b.model.hazards[i];
    rows.push({ id: ha.id, group: "hazard", label: ha.name, a: ha.ok ? withScore(ha.raw, ha.score) : null, b: hb?.ok ? withScore(hb.raw, hb.score) : null, leans: lean(ha.ok ? ha.score : null, hb?.ok ? hb.score : null, false) });
  }
  rows.push({ id: "exposure", group: "hazard", label: "Combined exposure", a: a.model.exposure === null ? null : formatScore(a.model.exposure), b: b.model.exposure === null ? null : formatScore(b.model.exposure), leans: lean(a.model.exposure, b.model.exposure, false) });

  rows.push({ id: "wb", group: "wellbeing", label: "Wellbeing", a: withScore(a.model.wellbeing.value, a.model.wellbeing.score), b: withScore(b.model.wellbeing.value, b.model.wellbeing.score), leans: lean(a.model.wellbeing.score, b.model.wellbeing.score, true) });

  for (const [i, la] of a.model.life.entries()) {
    const lb = b.model.life[i];
    const d = dims.find((x) => x.id === la.id);
    const comparable = la.kind === "score";
    rows.push({
      id: la.id,
      group: "life",
      label: la.name,
      a: la.res === "none" ? null : (withScore(la.value, la.score) ?? la.value),
      b: !lb || lb.res === "none" ? null : (withScore(lb.value, lb.score) ?? lb.value),
      leans: comparable ? lean(la.res === "none" ? null : la.score, !lb || lb.res === "none" ? null : lb.score, d?.higher_is !== "worse") : null,
    });
  }
  return rows;
}
