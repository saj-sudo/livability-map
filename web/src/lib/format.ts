// Human-readable values for the inspector, tooltip and compare panel. Known dimensions get
// their units; anything the manifest adds later falls through to a generic number, with the
// registry note carrying the meaning. A missing value is null, never "0" (invariant 3).

import type { DimInfo, Unit } from "./dims";

const DROUGHT_LABELS: Record<number, string> = { 0: "low", 1: "low to medium", 2: "medium", 3: "medium to high", 4: "high" };
const WSTRESS_LABELS: Record<number, string> = { [-1]: "arid and low water use (not scored)", 0: "low", 1: "low to medium", 2: "medium to high", 3: "high", 4: "extremely high" };

export function formatHazardRaw(id: string, v: number | null): string | null {
  if (v === null) return null;
  if (id === "heat") return `${Math.round(v)} days/yr`;
  if (id === "rflood" || id === "cflood") return `${(100 * v).toFixed(1)}% of area`;
  if (id === "wstress") return WSTRESS_LABELS[v] ?? String(v);
  return formatNumber(v);
}

/** The unit for a hex's value: the joiner tagged like the hex, else the dimension default, else
 *  the only unit there is. */
export function unitFor(d: DimInfo, res: string): Unit | null {
  const u = d.units ?? {};
  return u[res] ?? u["*"] ?? Object.values(u)[0] ?? null;
}

/** `raw` printed from the registry's unit: factor, decimals, then the unit text (no space
 *  before a leading %, / or °). New dimensions get this for free; the cases below only exist
 *  where the wording is nicer than "number unit". */
export function formatWithUnit(d: DimInfo, raw: number, res: string): string | null {
  const u = unitFor(d, res);
  if (!u) return null;
  const v = raw * u.multiply;
  const text = v.toLocaleString("en-US", { minimumFractionDigits: u.decimals, maximumFractionDigits: u.decimals });
  return /^[%/°]/.test(u.unit) ? `${text}${u.unit}` : `${text} ${u.unit}`;
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
    case "incmix":
      return oecd ? `${(100 * raw).toFixed(0)}% above the $4.20/day line` : `income mix ${raw.toFixed(2)} (0-1)`;
    case "house":
      return oecd ? `${raw.toFixed(1)} / 10 (OECD, higher = worse)` : `${raw.toFixed(0)}% of income on rent`;
    case "health":
      return oecd ? `${raw.toFixed(1)} / 10 (OECD health score)` : `${raw.toFixed(1)} physicians per 10,000`;
    case "cost":
      // BEA parities (county = metro area, admin1 = state) are relative to the US average; the
      // national ICP / WDI value is relative to the world average
      return `index ${Math.round(raw)} (${res === "national" ? "world" : "US"} = 100)`;
    case "rent":
      return `$${Math.round(raw).toLocaleString("en-US")}/month (2-bedroom FMR)`;
    case "drought":
      return `drought risk ${Math.round(raw)} of 4 (${DROUGHT_LABELS[Math.round(raw)] ?? "unknown"})`;
    default:
      // everything else (transit, school, lgbtq, the hex-level layers, any future dimension)
      // prints from the manifest's unit fields
      return formatWithUnit(d, raw, res) ?? formatNumber(raw);
  }
}

export const formatScore = (s: number): string => `${Math.round(s)}/100`;

export function formatPopulation(pop: number | null): string {
  return pop === null ? "population unknown" : `${pop.toLocaleString("en-US")} people`;
}
