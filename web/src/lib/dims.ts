// Client-side dimension registry (SPEC §20.2) derived from the manifest at build time, plus the
// canonical order used by the `w=` URL parameter. New dimensions are appended to DIM_ORDER so
// old links keep their meaning.

import type { DimGroup, DimKind, Manifest, ManifestDimension } from "./manifest";

export interface DimInfo {
  id: string;
  name: string;
  group: DimGroup;
  kind: DimKind;
  higher_is: "better" | "worse";
  /** coverage chip text: Global / OECD / US only */
  chip: string;
  note: string;
  scale: "percentile" | "minmax";
}

export const HAZARD_IDS = ["heat", "rflood", "cflood", "wstress"] as const;
// append-only: the position of each id is its slot in the `w=` URL parameter
export const DIM_ORDER = ["heat", "rflood", "cflood", "wstress", "wb", "jobs", "transit", "school", "lgbtq", "pol", "race", "incmix", "house", "health", "cost", "rent", "care", "air", "trees", "net", "fire", "drought"] as const;

export const HAZARD_RAW: Record<string, { attr: string; unit: string; label: string }> = {
  heat: { attr: "heat_days", unit: "days/yr", label: "days above 35 °C" },
  rflood: { attr: "rflood_frac", unit: "% of area", label: "riverine 1-in-100 flood" },
  cflood: { attr: "cflood_frac", unit: "% of area", label: "coastal 1-in-100 flood" },
  wstress: { attr: "wstress_cat", unit: "category 0-4", label: "water stress 2050" },
};

// Fallback registry when the manifest is empty (CI builds without data); ids, kinds and
// directions mirror pipeline/dimensions.yaml.
const FALLBACK: DimInfo[] = [
  { id: "heat", name: "Extreme heat", group: "hazard", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
  { id: "rflood", name: "Riverine flood", group: "hazard", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
  { id: "cflood", name: "Coastal flood", group: "hazard", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
  { id: "wstress", name: "Water stress", group: "hazard", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
  { id: "wb", name: "Wellbeing", group: "wellbeing", kind: "score", higher_is: "better", chip: "Global", note: "", scale: "minmax" },
  { id: "jobs", name: "Early-career job market", group: "life", kind: "score", higher_is: "better", chip: "Global / OECD / US", note: "", scale: "percentile" },
  { id: "transit", name: "Public transit access", group: "life", kind: "score", higher_is: "better", chip: "US only", note: "", scale: "percentile" },
  { id: "school", name: "Schools", group: "life", kind: "score", higher_is: "better", chip: "US only", note: "", scale: "percentile" },
  { id: "lgbtq", name: "LGBTQ+ presence", group: "life", kind: "score", higher_is: "better", chip: "US only", note: "", scale: "percentile" },
  { id: "pol", name: "Political lean", group: "life", kind: "signed", higher_is: "better", chip: "US only", note: "", scale: "percentile" },
  { id: "race", name: "Racial and ethnic composition", group: "life", kind: "composition", higher_is: "better", chip: "US only", note: "", scale: "percentile" },
  { id: "incmix", name: "Income mix", group: "life", kind: "score", higher_is: "better", chip: "Global / US", note: "", scale: "percentile" },
  { id: "house", name: "Housing cost burden", group: "life", kind: "score", higher_is: "worse", chip: "OECD / US", note: "", scale: "percentile" },
  { id: "health", name: "Healthcare access", group: "life", kind: "score", higher_is: "better", chip: "OECD / US", note: "", scale: "percentile" },
  // a higher price level or rent is worse for the person, so both point the other way
  { id: "cost", name: "Cost of living (price level)", group: "life", kind: "score", higher_is: "worse", chip: "Global / US", note: "", scale: "percentile" },
  { id: "rent", name: "Housing cost (rent level)", group: "life", kind: "score", higher_is: "worse", chip: "US only", note: "", scale: "percentile" },
  // hex-level layers (2026-09-22): global rasters and point sets computed per hex
  { id: "care", name: "Travel time to healthcare", group: "life", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
  { id: "air", name: "Air quality (fine particulate matter)", group: "env", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
  { id: "trees", name: "Tree cover", group: "env", kind: "score", higher_is: "better", chip: "Global", note: "", scale: "percentile" },
  { id: "net", name: "Internet speed", group: "life", kind: "score", higher_is: "better", chip: "Global", note: "", scale: "percentile" },
  { id: "fire", name: "Wildfire (burned area)", group: "env", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
  { id: "drought", name: "Drought risk", group: "env", kind: "score", higher_is: "worse", chip: "Global", note: "", scale: "percentile" },
];

const CHIP: Record<string, string> = { global: "Global", oecd: "OECD", us: "US" };

function chipFor(coverage: unknown): string {
  if (!Array.isArray(coverage) || coverage.length === 0) return "";
  const parts = coverage.map((c) => CHIP[String(c)] ?? String(c));
  return parts.length === 1 && parts[0] === "US" ? "US only" : parts.join(" / ");
}

function fromManifest(d: ManifestDimension): DimInfo {
  return {
    id: d.id,
    name: d.name,
    group: d.group,
    kind: d.kind,
    higher_is: d.higher_is,
    chip: chipFor(d.coverage),
    note: d.note ?? "",
    scale: d.scale ?? "percentile",
  };
}

/** Dimensions in DIM_ORDER, taken from the manifest when it has any, else the fallback. */
export function dimensionsFrom(manifest: Manifest): DimInfo[] {
  const entries = [...(manifest.hazards ?? []), ...(manifest.dimensions ?? [])];
  if (entries.length === 0) return FALLBACK;
  const byId = new Map(entries.map((d) => [d.id, fromManifest(d)]));
  const ordered = DIM_ORDER.filter((id) => byId.has(id)).map((id) => byId.get(id)!);
  const extra = entries.map((d) => d.id).filter((id) => !(DIM_ORDER as readonly string[]).includes(id));
  return [...ordered, ...extra.map((id) => byId.get(id)!)];
}

export const lifeDims = (dims: DimInfo[]) => dims.filter((d) => d.group === "life");
export const envDims = (dims: DimInfo[]) => dims.filter((d) => d.group === "env");
export const hazardDims = (dims: DimInfo[]) => dims.filter((d) => d.group === "hazard");

/** Badge text for a resolution tag (SPEC §6.1); unknown tags show as they are. */
export const RES_LABELS: Record<string, string> = { hex: "this hex", basin: "sub-basin", admin1: "region", county: "county", tract: "tract", national: "national", none: "no data" };
export const resLabel = (tag: string): string => RES_LABELS[tag] ?? tag;
