// The place panel's lead lines (SPEC §10, §13.50): at most five findings, each with its figure,
// picked by one fixed rule so the same hexagon always reads the same way. Everything else sits
// behind "All measures and their sources". Missing data is named as missing, never folded into a
// number (invariant 3). Pure and small so the wording can change without touching the panel;
// lead.test.ts pins the facts each line must carry.

import { compositeValue, FIT_WORDS, fitBand, type Bar } from "./chart";
import { HAZARD_IDS, resLabel, shortName, type DimInfo } from "./dims";
import type { Picks, Weights } from "./expressions";
import type { HexModel, LifeRow } from "./inspect";

export type LeadKey = "note" | "climate" | "fit" | "wellbeing" | "today" | "missing";

export interface LeadLine {
  key: LeadKey;
  label: string;
  text: string;
}

/** How far from the middle a present-day rank must be to earn the "today" line. */
export const TODAY_MIN_DISTANCE = 25;
/** How many missing measures are named before "and N more". */
export const MISSING_NAMED = 4;

const LEVELS = ["Low", "Fairly low", "Middling", "Fairly high", "High"];
/** Combined exposure in words, on the same five steps as the map's ramp (§9.3). */
export const exposureLevel = (score: number): string => LEVELS[Math.min(4, Math.max(0, Math.floor(score / 20)))];

const lower = (name: string): string => (/^[A-Z]{2}/.test(name) ? name : name.charAt(0).toLowerCase() + name.slice(1));
const list = (names: string[]): string => (names.length <= 1 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);
const rank = (score: number): string => `higher than ${Math.round(score)}% of inhabited places`;

function climateLine(m: HexModel): LeadLine | null {
  const present = m.hazards.filter((h) => h.ok && h.score !== null);
  if (m.exposure === null || !present.length) return null;
  const top = present.reduce((a, b) => (b.score! > a.score! ? b : a));
  const parts = [`${exposureLevel(m.exposure)}: ${Math.round(m.exposure)} of 100, the average of the hazard ranks here.`];
  parts.push(`${shortName(top.name)} ranks highest${top.raw ? ` (${top.raw}, ${rank(top.score!)})` : ` (${rank(top.score!)})`}.`);
  if (m.coverageN < HAZARD_IDS.length) parts.push(`Only ${m.coverageN} of ${HAZARD_IDS.length} hazard layers have data, so this is less certain.`);
  return { key: "climate", label: "Climate in 2050", text: parts.join(" ") };
}

function fitLine(bars: Bar[], dims: DimInfo[], weights: Weights, picks: Picks, props: Record<string, unknown>, presetName: string | null): LeadLine | null {
  if (!bars.length) return null;
  const label = presetName ? `Fit with ${presetName}` : "Fit with your priorities";
  const c = compositeValue(dims, weights, picks, props);
  if (c === null) return { key: "fit", label, text: "None of the measures you weighted has data here, so there is no fit to show." };
  const have = bars.filter((b) => b.match !== null);
  const up = have.filter((b) => b.match! >= 67).sort((a, b) => b.match! - a.match!).slice(0, 2);
  const down = have.filter((b) => b.match! <= 33).sort((a, b) => a.match! - b.match!).slice(0, 2);
  const out = bars.filter((b) => b.match === null);
  const band = FIT_WORDS[fitBand(c)];
  const parts = [`A ${band}.`];
  if (up.length) parts.push(`Pulled up by ${list(up.map((b) => lower(shortName(b.name))))}.`);
  if (down.length) parts.push(`Pulled down by ${list(down.map((b) => lower(shortName(b.name))))}.`);
  if (out.length) parts.push(`Left out for lack of data: ${list(out.slice(0, MISSING_NAMED).map((b) => lower(shortName(b.name))))}${out.length > MISSING_NAMED ? ` and ${out.length - MISSING_NAMED} more` : ""}.`);
  return { key: "fit", label, text: parts.join(" ") };
}

function wellbeingLine(m: HexModel): LeadLine | null {
  if (!m.inhabited || m.wellbeing.value === null || m.wellbeing.res === "none") return null;
  if (m.wellbeing.res === "national") {
    return { key: "wellbeing", label: "Wellbeing", text: `Only a national figure exists here (${m.wellbeing.value}). It says nothing about this area in particular.` };
  }
  return { key: "wellbeing", label: "Wellbeing", text: `${m.wellbeing.value}, a ${resLabel(m.wellbeing.res)}.` };
}

function todayLine(m: HexModel, dims: DimInfo[]): LeadLine | null {
  const ranked = new Set(dims.filter((d) => d.kind === "score" && d.scale === "percentile").map((d) => d.id));
  let best: LifeRow | null = null;
  for (const row of [...m.env, ...m.life]) {
    if (row.score === null || row.res === "none" || !ranked.has(row.id)) continue;
    if (!best || Math.abs(row.score - 50) > Math.abs(best.score! - 50)) best = row;
  }
  if (!best || Math.abs(best.score! - 50) < TODAY_MIN_DISTANCE) return null;
  const value = best.value ? `${best.value}; ` : "";
  return { key: "today", label: "Stands out today", text: `${shortName(best.name)}: ${value}${rank(best.score!)}. More of it is ${best.higherIs === "worse" ? "worse" : "better"}.` };
}

function missingLine(m: HexModel): LeadLine | null {
  const names: string[] = [];
  for (const h of m.hazards) if (!h.ok || h.score === null) names.push(shortName(h.name));
  if (m.inhabited && (m.wellbeing.value === null || m.wellbeing.res === "none")) names.push("Wellbeing");
  if (m.inhabited) for (const row of [...m.env, ...m.life]) if (row.res === "none") names.push(shortName(row.name));
  if (!names.length) return null;
  const shown = names.slice(0, MISSING_NAMED).map(lower);
  const more = names.length - shown.length;
  return { key: "missing", label: "Not measured here", text: `${list(shown).replace(/^./, (c) => c.toUpperCase())}${more > 0 ? `, and ${more} more` : ""}. No data, which is not the same as zero.` };
}

export function leadLines(m: HexModel, bars: Bar[], dims: DimInfo[], weights: Weights, picks: Picks, props: Record<string, unknown>, presetName: string | null = null): LeadLine[] {
  const lines: (LeadLine | null)[] = [];
  if (!m.inhabited) lines.push({ key: "note", label: "Almost no one lives here", text: "Fewer than 100 people live here, so wellbeing and life measures are not scored. The hazards are still projected." });
  else if (m.coverageN === 0) lines.push({ key: "note", label: "Climate in 2050", text: "No hazard layer has data here, so exposure is not shown. That is missing data, not zero risk." });
  lines.push(climateLine(m), m.inhabited ? fitLine(bars, dims, weights, picks, props, presetName) : null, wellbeingLine(m), m.inhabited ? todayLine(m, dims) : null, missingLine(m));
  return lines.filter((l): l is LeadLine => l !== null).slice(0, 5);
}
