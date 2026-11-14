// Client-side dimension registry (SPEC §20.2) derived from the manifest at build time, plus the
// canonical order used by the `w=` URL parameter. New dimensions are appended to DIM_ORDER so
// old links keep their meaning; dimensions the manifest adds that are not in DIM_ORDER yet are
// listed after it (they still get sliders, rows and colours; only the URL slot is missing).

import type { DimGroup, DimKind, Manifest, ManifestDimension } from "./manifest";

export interface DimInfo {
  id: string;
  name: string;
  group: DimGroup;
  kind: DimKind;
  higher_is: "better" | "worse";
  /** coverage chip text: Global / OECD / US only / EU cities */
  chip: string;
  note: string;
  scale: "percentile" | "minmax";
  /** false when the manifest shows no hex with a value (e.g. a source still pending) */
  available: boolean;
  /** how to print the raw value, keyed by resolution tag; "*" is the dimension-level default
   *  (optional so test fixtures and older callers need not state it) */
  units?: Record<string, Unit>;
}

export interface Unit {
  unit: string;
  multiply: number;
  decimals: number;
}

/** Units per resolution tag from the manifest joiners (first joiner per tag wins, like the
 *  first-hit-wins join itself), plus the dimension's own unit under "*". */
export function unitsFrom(d: Pick<ManifestDimension, "joiners" | "unit" | "multiply" | "decimals">): Record<string, Unit> {
  const out: Record<string, Unit> = {};
  if (d.unit) out["*"] = { unit: d.unit, multiply: d.multiply ?? 1, decimals: d.decimals ?? 1 };
  for (const j of d.joiners ?? []) if (j.unit && !(j.res in out)) out[j.res] = { unit: j.unit, multiply: j.multiply ?? 1, decimals: j.decimals ?? 1 };
  return out;
}

/** The hazards, in panel order; coverage runs from 0 to HAZARD_IDS.length. Humid heat is the
 *  fifth, beside dry heat (SPEC §13.47), so heat weighs twice in combined exposure. */
export const HAZARD_IDS = ["heat", "humid", "rflood", "cflood", "wstress"] as const;
/** The `w=` URL order: append only, so old links keep their meaning (humid came after industry). */
export const DIM_ORDER = ["heat", "rflood", "cflood", "wstress", "wb", "jobs", "transit", "school", "lgbtq", "pol", "race", "incmix", "house", "health", "cost", "rent", "care", "air", "trees", "net", "fire", "drought", "city", "wealth", "conflict", "walkcare", "water", "nri", "phealth", "industry", "humid", "no2", "amen", "immig", "safe", "opp", "opp25"] as const;
/** Display order: the hazards as HAZARD_IDS lists them (humid heat beside heat), then DIM_ORDER. */
export const DISPLAY_ORDER: readonly string[] = [...HAZARD_IDS, ...DIM_ORDER.filter((id) => !(HAZARD_IDS as readonly string[]).includes(id))];

export const HAZARD_RAW: Record<string, { attr: string; unit: string; label: string }> = {
  heat: { attr: "heat_days", unit: "days/yr", label: "days above 35 °C" },
  humid: { attr: "humid_days", unit: "days/yr", label: "days with heat index above 35 °C" },
  rflood: { attr: "rflood_frac", unit: "% of area", label: "riverine 1-in-100 flood" },
  cflood: { attr: "cflood_frac", unit: "% of area", label: "coastal 1-in-100 flood" },
  wstress: { attr: "wstress_cat", unit: "category 0-4", label: "water stress 2050" },
};

// Fallback registry when the manifest is empty (CI builds without data); ids, kinds and
// directions mirror pipeline/dimensions.yaml.
const F = (id: string, name: string, group: DimGroup, kind: DimKind, higher_is: "better" | "worse", chip: string, scale: "percentile" | "minmax" = "percentile"): DimInfo => ({ id, name, group, kind, higher_is, chip, note: "", scale, available: true, units: {} });
const FALLBACK: DimInfo[] = [
  F("heat", "Extreme heat", "hazard", "score", "worse", "Global"),
  F("humid", "Humid heat (heat index > 35 °C)", "hazard", "score", "worse", "Global"),
  F("rflood", "Riverine flood", "hazard", "score", "worse", "Global"),
  F("cflood", "Coastal flood", "hazard", "score", "worse", "Global"),
  F("wstress", "Water stress", "hazard", "score", "worse", "Global"),
  F("wb", "Wellbeing", "wellbeing", "score", "better", "Global", "minmax"),
  F("jobs", "Early-career job market", "life", "score", "better", "Global / OECD / US"),
  F("transit", "Public transit access", "life", "score", "better", "US only"),
  F("school", "Schools", "life", "score", "better", "US only"),
  F("lgbtq", "LGBTQ+ presence and acceptance", "life", "score", "better", "US / EU cities"),
  F("pol", "Political lean", "life", "signed", "better", "US only"),
  F("race", "Racial and ethnic composition", "life", "composition", "better", "US only"),
  F("incmix", "Income mix", "life", "score", "better", "Global / US"),
  F("house", "Housing cost burden", "life", "score", "worse", "OECD / US"),
  F("health", "Healthcare access", "life", "score", "better", "OECD / US"),
  // cost of living (a higher price level or rent is worse for the person)
  F("cost", "Cost of living (price level)", "life", "score", "worse", "Global / US"),
  F("rent", "Housing cost (rent level)", "life", "score", "worse", "US only"),
  // hex-level layers (2026-09-22): global rasters and point sets computed per hex
  F("care", "Travel time to healthcare", "life", "score", "worse", "Global"),
  F("air", "Air quality (fine particulate matter)", "env", "score", "worse", "Global"),
  F("trees", "Tree cover", "env", "score", "better", "Global"),
  F("net", "Internet speed", "life", "score", "better", "Global"),
  F("fire", "Wildfire (burned area)", "env", "score", "worse", "Global"),
  F("drought", "Drought risk", "env", "score", "worse", "Global"),
  F("city", "Access to a city", "life", "score", "worse", "Global"),
  F("wealth", "Relative wealth", "life", "score", "better", "Within country"),
  F("conflict", "Armed conflict nearby", "life", "score", "worse", "Global"),
  F("walkcare", "Walking time to healthcare", "life", "score", "worse", "Global"),
  F("water", "Working water points nearby", "life", "score", "better", "Global"),
  // US tract layers (2026-11, SPEC §13.38)
  F("nri", "Natural hazard losses today (US)", "env", "score", "worse", "US only"),
  F("phealth", "Adults in fair or poor health (US)", "life", "score", "worse", "US only"),
  F("industry", "Heavy industry nearby", "env", "score", "worse", "Global"),
  F("no2", "Traffic and combustion pollution (NO2)", "env", "score", "worse", "Global"),
  F("amen", "Everyday amenities nearby", "life", "score", "better", "Global"),
  // EU cities perception survey and the Opportunity Atlas (2026-11, SPEC §13.48)
  F("immig", "Welcoming to immigrants (EU cities)", "life", "score", "better", "EU cities"),
  F("safe", "Feeling safe at night (EU cities)", "life", "score", "better", "EU cities"),
  F("opp", "Kids' adult income, all families (US)", "life", "score", "better", "US only"),
  F("opp25", "Upward mobility: kids from low-income families (US)", "life", "score", "better", "US only"),
];

/** Composition dimensions (racial and ethnic composition) are context in the place panel, never
 *  a priority: weighting one sorts neighbourhoods by who lives there, which is steering
 *  (SPEC §3, decision §13.40). No slider, no part in the composite, ignored in old links. */
export const weightable = (d: Pick<DimInfo, "kind">): boolean => d.kind !== "composition";
export const CONTEXT_ONLY_IDS: ReadonlySet<string> = new Set(FALLBACK.filter((d) => !weightable(d)).map((d) => d.id));

// scoring domains (§20.4) -> chip text; country domains are small-area or grid sources of one country
const CHIP: Record<string, string> = { global: "Global", oecd: "OECD", us: "US", eu: "EU", eucities: "EU cities", uk: "England", de: "Germany", nl: "Netherlands", fr: "France", ca: "Canada", au: "Australia", country: "Within country" };
/** A scoring domain (§20.4) in words; "country:TZ" style per-country domains read "within country". */
export const domainLabel = (k: string): string => CHIP[k.split(":")[0]] ?? k;
const DOMAIN_ORDER = ["global", "oecd", "us", "eu", "eucities", "uk", "de", "nl", "fr", "ca", "au", "country"];

/**
 * Coverage chip. The manifest overwrites a dimension's `coverage` list with per-resolution
 * tag counts, so the scoring domains are read from `domains` (res -> domain -> hexes) first,
 * then from the joiners, then from a plain string list (hazards, fixtures).
 */
export function chipFor(d: Pick<ManifestDimension, "coverage" | "domains" | "joiners">): string {
  const found = new Set<string>();
  // a per-country domain ("country:TZ", values relative within a country) counts as one chip
  for (const perRes of Object.values(d.domains ?? {})) for (const [k, n] of Object.entries(perRes)) if (n > 0) found.add(k.split(":")[0]);
  if (!found.size) for (const j of d.joiners ?? []) if (j.domain) found.add(j.domain);
  if (!found.size && Array.isArray(d.coverage)) for (const c of d.coverage) found.add(String(c));
  const parts = DOMAIN_ORDER.filter((k) => found.has(k)).map((k) => CHIP[k]);
  for (const k of found) if (!DOMAIN_ORDER.includes(k)) parts.push(k);
  if (!parts.length) return "";
  return parts.length === 1 && parts[0] === "US" ? "US only" : parts.join(" / ");
}

/** Any hex with a value at any resolution? (`coverage` as res -> tag -> count; tag `none` excluded) */
export function isAvailable(d: Pick<ManifestDimension, "coverage">): boolean {
  const c = d.coverage as unknown;
  if (!c || Array.isArray(c)) return true; // hazards and fixtures list domains, not counts
  for (const perRes of Object.values(c as Record<string, Record<string, number>>)) {
    for (const [tag, n] of Object.entries(perRes)) if (tag !== "none" && n > 0) return true;
  }
  return false;
}

function fromManifest(d: ManifestDimension): DimInfo {
  return {
    id: d.id,
    name: d.name,
    group: d.group,
    kind: d.kind,
    higher_is: d.higher_is,
    chip: chipFor(d),
    note: d.note ?? "",
    scale: d.scale ?? "percentile",
    available: isAvailable(d),
    units: unitsFrom(d),
  };
}

/** Dimensions in DISPLAY_ORDER, taken from the manifest when it has any, else the fallback. */
export function dimensionsFrom(manifest: Manifest): DimInfo[] {
  const entries = [...(manifest.hazards ?? []), ...(manifest.dimensions ?? [])];
  if (entries.length === 0) return FALLBACK;
  const byId = new Map(entries.map((d) => [d.id, fromManifest(d)]));
  const ordered = DISPLAY_ORDER.filter((id) => byId.has(id)).map((id) => byId.get(id)!);
  const extra = entries.map((d) => d.id).filter((id) => !DISPLAY_ORDER.includes(id));
  return [...ordered, ...extra.map((id) => byId.get(id)!)];
}

/** Panel-length name: the registry's trailing parenthetical is a definition, shown as a tooltip instead. */
export const shortName = (name: string): string => name.replace(/\s*\([^)]*\)\s*$/, "");

export const lifeDims = (dims: DimInfo[]) => dims.filter((d) => d.group === "life");
export const envDims = (dims: DimInfo[]) => dims.filter((d) => d.group === "env");

/** Plain words for a resolution tag (SPEC §6.1): the badge beside a value in the place panel, the
 *  wellbeing line and the /methodology tables all read this one map. Unknown tags show as they are. */
export const RES_LABELS: Record<string, string> = {
  hex: "this area",
  grid: "1 km grid cells",
  basin: "river basin",
  tract: "census tract",
  area: "small-area figure",
  city: "city survey",
  county: "county figure",
  admin1: "regional figure",
  national: "national figure",
  none: "no data here",
};
export const resLabel = (tag: string): string => RES_LABELS[tag] ?? tag;
