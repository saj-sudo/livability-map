// Human-readable values for the inspector, tooltip and compare panel. Known dimensions get
// their units; anything the manifest adds later falls through to a generic number, with the
// registry note carrying the meaning. A missing value is null, never "0" (invariant 3).

import type { DimInfo } from "./dims";

const WSTRESS_LABELS: Record<number, string> = { [-1]: "arid and low water use (not scored)", 0: "low", 1: "low to medium", 2: "medium to high", 3: "high", 4: "extremely high" };

export function formatHazardRaw(id: string, v: number | null): string | null {
  if (v === null) return null;
  if (id === "heat") return `${Math.round(v)} days/yr`;
  if (id === "rflood" || id === "cflood") return `${(100 * v).toFixed(1)}% of area`;
  if (id === "wstress") return WSTRESS_LABELS[v] ?? String(v);
  return formatNumber(v);
}

/** Plain number: integers as-is, otherwise two decimals, thousands separated. */
export function formatNumber(v: number): string {
  return Number.isInteger(v) ? v.toLocaleString("en-US") : v.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/**
 * A life dimension's raw value with its unit. The resolution tag says which source produced
 * the value: tract/county = US layers, admin1 = OECD (0-10 scores) or GSAP (share),
 * national = ILOSTAT (percent).
 */
export function formatDimRaw(d: DimInfo, raw: number | null, res: string): string | null {
  if (raw === null) return null;
  const oecd = res === "admin1";
  switch (d.id) {
    case "jobs":
      if (oecd) return `${raw.toFixed(1)} / 10 (OECD jobs score)`;
      if (res === "national") return `${raw.toFixed(0)}% of 15-24s employed`;
      return `${(100 * raw).toFixed(0)}% employed`;
    case "transit":
      return `${raw.toFixed(1)} transit trips/hour nearby`;
    case "school":
      return `${raw.toFixed(0)}% graduate on time`;
    case "lgbtq":
      return `${raw.toFixed(1)} same-sex couples per 1,000 households`;
    case "incmix":
      return oecd ? `${(100 * raw).toFixed(0)}% above the $4.20/day line` : `income mix ${raw.toFixed(2)} (0-1)`;
    case "house":
      return oecd ? `${raw.toFixed(1)} / 10 (OECD, higher = worse)` : `${raw.toFixed(0)}% of income on rent`;
    case "health":
      return oecd ? `${raw.toFixed(1)} / 10 (OECD health score)` : `${raw.toFixed(1)} physicians per 10,000`;
    default:
      return formatNumber(raw);
  }
}

export const formatScore = (s: number): string => `${Math.round(s)}/100`;

export function formatPopulation(pop: number | null): string {
  return pop === null ? "population unknown" : `${pop.toLocaleString("en-US")} people`;
}
