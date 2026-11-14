// Plain words for the codes the manifest carries, for /methodology (SPEC §10): a reader sees
// "ranked 0-100 among inhabited places" and "licence checked by search", never "score
// (percentile, higher = better)" or "Verified: search".

import type { ManifestDimension } from "./manifest";

type KindFields = Pick<ManifestDimension, "kind" | "higher_is" | "scale" | "group">;

/** What a dimension's number is, in a sentence fragment. */
export function kindWords(d: KindFields): string {
  if (d.kind === "signed") return "A lean to one side (for example D+10), not ranked";
  if (d.kind === "composition") return "Shares of groups, shown as context only; never ranked or weighted";
  const direction = d.group === "hazard" ? "higher means more exposure" : d.higher_is === "worse" ? "higher is worse" : "higher is better";
  if (d.scale === "minmax") return `Scaled 0-100 within its source; ${direction}`;
  return `Ranked 0-100 among inhabited places; ${direction}`;
}

const VERIFIED: Record<string, string> = {
  confirmed: "Licence and download checked first-hand",
  search: "Licence checked by search; first-hand check pending",
  none: "Not checked yet",
};

/** A source's `verified` code in words; unknown codes show as they are. */
export const verifiedWords = (v: string): string => VERIFIED[v] ?? v;
