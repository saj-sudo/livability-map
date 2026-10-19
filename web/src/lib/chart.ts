// TypeScript twin of the priorities match (SPEC §20.5) for the inspector's bars, the tooltip
// and the compare panel. The map colours come from expressions.ts (a MapLibre expression);
// chart.test.ts proves the two agree, so the number a person reads is the number the hex
// is coloured by. Missing stays null (invariant 3), never 0.

import { weightable, type DimInfo } from "./dims";
import { hasAttr, type Picks, type Weights } from "./expressions";

export type Props = Record<string, unknown>;

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** 0..100 match of one dimension on a hex, or null when the hex has no value for it (or the
 *  dimension is context only, §13.39). */
export function matchValue(d: DimInfo, props: Props, picks: Picks): number | null {
  if (!weightable(d)) return null;
  if (!(hasAttr(d) in props) || props[hasAttr(d)] === null || props[hasAttr(d)] === undefined) return null;
  if (d.kind === "score") {
    const s = num(props[`${d.id}_score`]);
    if (s === null) return null;
    return d.higher_is === "worse" ? 100 - s : s;
  }
  if (d.kind === "signed") {
    const lean = num(props[`${d.id}_lean`]);
    if (lean === null) return null;
    if (picks.pol === "left") return (lean + 100) / 2;
    if (picks.pol === "right") return (100 - lean) / 2;
    return 100 - Math.abs(lean);
  }
  return null;
}

/** Weighted mean of the matches over the dimensions the hex has; null when none does. */
export function compositeValue(dims: DimInfo[], weights: Weights, picks: Picks, props: Props): number | null {
  let numr = 0;
  let den = 0;
  for (const d of dims) {
    const w = weightable(d) ? (weights[d.id] ?? 0) : 0;
    if (w <= 0) continue;
    const m = matchValue(d, props, picks);
    if (m === null) continue;
    numr += w * m;
    den += w;
  }
  return den > 0 ? numr / den : null;
}

export interface Bar {
  id: string;
  name: string;
  chip: string;
  weight: number;
  /** null = no data on this hex (drawn as an empty, hatched row) */
  match: number | null;
}

/** One row per weighted dimension, heaviest first, then registry order. */
export function priorityBars(props: Props, dims: DimInfo[], weights: Weights, picks: Picks): Bar[] {
  return dims
    .map((d, i) => ({ d, i, w: weightable(d) ? (weights[d.id] ?? 0) : 0 }))
    .filter((x) => x.w > 0)
    .sort((a, b) => b.w - a.w || a.i - b.i)
    .map(({ d, w }) => ({ id: d.id, name: d.name, chip: d.chip, weight: w, match: matchValue(d, props, picks) }));
}

/** How many weighted dimensions are missing on the hex, and how many there are. */
export function missingCount(bars: Bar[]): { missing: number; total: number } {
  return { missing: bars.filter((b) => b.match === null).length, total: bars.length };
}
