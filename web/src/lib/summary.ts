// One plain-language sentence or two about a hex for the top of the inspector (SPEC §10).
// It leads with what the map colour means, says how much of the hazard picture is there,
// flags a national wellbeing figure, and adds the priorities match when weights are set.
// Missing data is named as missing, never folded into a number (invariant 3).
//
// This function is deliberately small and isolated so the wording can be rewritten without
// touching anything else; summary.test.ts pins the facts each sentence must carry.

import { compositeValue, missingCount, type Bar } from "./chart";
import { HAZARD_IDS, type DimInfo } from "./dims";
import type { Picks, Weights } from "./expressions";
import { formatScore } from "./format";
import type { HexModel } from "./inspect";

const LEVEL = ["low", "medium", "high"];

/** "low climate exposure and high wellbeing" from a bivariate class, or null when unclassified. */
export function bivarPhrase(bivarClass: number): string | null {
  if (bivarClass < 1 || bivarClass > 9) return null;
  const exposure = LEVEL[(bivarClass - 1) % 3];
  const wellbeing = LEVEL[Math.floor((bivarClass - 1) / 3)];
  return `${exposure} climate exposure and ${wellbeing} wellbeing`;
}

/** "This area in Colorado": the summary is about the hex, not the whole region it sits in. */
export function areaPhrase(m: Pick<HexModel, "title">): string {
  return m.title && m.title !== "no country" ? `This area in ${m.title}` : "This area";
}

export function summarize(m: HexModel, bars: Bar[], dims: DimInfo[], weights: Weights, picks: Picks, props: Record<string, unknown>): string {
  const parts: string[] = [];
  const phrase = bivarPhrase(m.bivarClass);
  const where = areaPhrase(m);
  if (!m.inhabited) parts.push("Fewer than 100 people live here, so wellbeing and life dimensions are not scored; the hazards are still projected.");
  else if (phrase) parts.push(`${where} shows ${phrase}.`);
  else if (m.coverageN === 0) parts.push(`${where} has no hazard data, so it is not classified.`);
  else parts.push(`${where} has hazard data but no wellbeing figure, so it is not classified.`);

  if (m.coverageN === HAZARD_IDS.length) parts.push("All five hazard layers are present.");
  else if (m.coverageN > 0) parts.push(`Only ${m.coverageN} of ${HAZARD_IDS.length} hazard layers are present, so the exposure side is less certain.`);

  if (m.wellbeing.res === "national" && m.inhabited) parts.push("Wellbeing is the national figure, not this region's.");

  if (bars.length) {
    const c = compositeValue(dims, weights, picks, props);
    const { missing, total } = missingCount(bars);
    if (c === null) parts.push("None of your weighted layers has data here.");
    else parts.push(`It matches your priorities ${formatScore(c)}${missing ? `, with ${missing} of ${total} missing here` : ""}.`);
  }
  return parts.join(" ");
}
