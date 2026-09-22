// One plain-language sentence or two about a hex for the top of the inspector (SPEC §10).
// It leads with what the map colour means, says how much of the hazard picture is there,
// flags a national wellbeing figure, and adds the priorities match when weights are set.
// Missing data is named as missing, never folded into a number (invariant 3).
//
// This function is deliberately small and isolated so the wording can be rewritten without
// touching anything else; summary.test.ts pins the facts each sentence must carry.

import { compositeValue, missingCount, type Bar } from "./chart";
import type { DimInfo } from "./dims";
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

export function summarize(m: HexModel, bars: Bar[], dims: DimInfo[], weights: Weights, picks: Picks, props: Record<string, unknown>): string {
  const parts: string[] = [];
  const phrase = bivarPhrase(m.bivarClass);
  if (!m.inhabited) parts.push("Fewer than 100 people live here, so wellbeing and life dimensions are not scored; the hazards are still projected.");
  else if (phrase) parts.push(`${m.title} shows ${phrase}.`);
  else if (m.coverageN === 0) parts.push(`${m.title} has no hazard data, so it is not classified.`);
  else parts.push(`${m.title} has hazard data but no wellbeing figure, so it is not classified.`);

  if (m.coverageN === 4) parts.push("All four hazard layers are present.");
  else if (m.coverageN > 0) parts.push(`Only ${m.coverageN} of 4 hazard layers are present, so the exposure side is less certain.`);

  if (m.wellbeing.res === "national" && m.inhabited) parts.push("Wellbeing is the national figure, not this region's.");

  if (bars.length) {
    const c = compositeValue(dims, weights, picks, props);
    const { missing, total } = missingCount(bars);
    if (c === null) parts.push("None of your weighted dimensions has data here.");
    else parts.push(`It matches your priorities ${formatScore(c)}${missing ? `, with ${missing} of ${total} missing here` : ""}.`);
  }
  return parts.join(" ");
}
