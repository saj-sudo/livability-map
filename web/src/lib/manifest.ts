// Types mirroring pipeline/manifest.py (SPEC §6.3) plus the build-time loader used by server
// components. The manifest is the single source for /methodology, the inspector's sources list
// and the dimension registry the panel renders.

// hex = computed per hex from a raster or point set; basin = Aqueduct sub-basin at the centroid
export type ResTag = "hex" | "basin" | "admin1" | "county" | "tract" | "national" | "none";
export type DimKind = "score" | "signed" | "composition";
// env = present-day environment (air, trees, fire, drought): shown beside the 2050 hazards but
// never part of exposure / coverage (SPEC §13.28)
export type DimGroup = "hazard" | "wellbeing" | "life" | "env";
export type Domain = "global" | "oecd" | "us";

export interface ManifestSource {
  id: string;
  name: string;
  group: string;
  access: string;
  url: string | null;
  format: string;
  license: string;
  license_note: string;
  vintage: string;
  attribution: string;
  processing: string;
  files: string[];
  verified: string;
  checksums: Record<string, string>;
  [extra: string]: unknown;
}

export interface ManifestJoiner {
  source: string;
  joiner: string;
  res: ResTag;
  field: string;
  domain: Domain;
  label: string;
  weight_field?: string;
  fields?: Record<string, string>;
  /** how to print the raw value: text after the number, factor applied first, decimals shown */
  unit?: string;
  multiply?: number;
  decimals?: number;
}

export interface ManifestDimension {
  id: string;
  name: string;
  group: DimGroup;
  kind: DimKind;
  higher_is: "better" | "worse";
  coverage: string[];
  sources: string[];
  scale: "percentile" | "minmax";
  joiners: ManifestJoiner[];
  note: string;
  /** res -> tag -> inhabited hex count */
  coverage_by_res?: Record<string, Record<string, number>>;
  domains?: Record<string, Record<string, number>>;
  raw?: string;
  /** dimension-level unit (hazards; the default for joiners without their own) */
  unit?: string;
  multiply?: number;
  decimals?: number;
}

export interface Manifest {
  built_at: string | null;
  h3_res: number[];
  scenario: string;
  horizon: string;
  non_commercial: boolean;
  fixtures?: boolean;
  tiles: { hexes?: { key: string; sha256: string; bytes: number; layers: { name: string; minzoom: number; maxzoom: number }[]; minzoom: number; maxzoom: number } };
  sources: ManifestSource[];
  hazards: ManifestDimension[];
  dimensions: (ManifestDimension & { coverage: Record<string, Record<string, number>> | string[] })[];
  coverage_summary: Record<string, Record<string, number | Record<string, number> | null>>;
  spot_checks: Record<string, Record<string, unknown>[]>;
  processing_notes: string[];
  known_gaps: Record<string, Record<string, Record<string, unknown>>>;
  timings?: Record<string, Record<string, unknown>>;
  published_at?: string;
  public_base_url?: string | null;
}

/** The manifest the pipeline writes carries dimension `coverage` as res -> tag counts (the
 *  registry's coverage chips list lives in `coverage` of the registry entry); normalise both. */
export function coverageChips(d: ManifestDimension | { coverage: unknown }): string[] {
  const c = (d as { coverage: unknown }).coverage;
  return Array.isArray(c) ? (c as string[]) : [];
}

export const EMPTY_MANIFEST: Manifest = {
  built_at: null,
  h3_res: [],
  scenario: "rcp45_ssp245",
  horizon: "2050",
  non_commercial: true,
  tiles: {},
  sources: [],
  hazards: [],
  dimensions: [],
  coverage_summary: {},
  spot_checks: {},
  processing_notes: [],
  known_gaps: {},
};

/**
 * Build-time loader (server components only). Order: public/data/manifest.json on disk, then
 * NEXT_PUBLIC_DATA_BASE/manifest.json over HTTP, else the empty manifest with a warning so CI
 * builds without data still succeed (the pages then say that no build is loaded).
 */
export async function loadManifest(): Promise<Manifest> {
  const { existsSync } = await import("node:fs");
  const { readFile } = await import("node:fs/promises");
  const path = await import("node:path");
  const local = path.join(process.cwd(), "public", "data", "manifest.json");
  if (existsSync(local)) {
    return JSON.parse(await readFile(local, "utf8")) as Manifest;
  }
  const base = process.env.NEXT_PUBLIC_DATA_BASE;
  if (base && /^https?:/.test(base)) {
    try {
      const resp = await fetch(`${base.replace(/\/$/, "")}/manifest.json`);
      if (resp.ok) return (await resp.json()) as Manifest;
      console.warn(`manifest fetch failed: ${resp.status}`);
    } catch (err) {
      console.warn("manifest fetch failed:", err);
    }
  }
  console.warn("no manifest.json found (run `python -m pipeline publish --target local` or set NEXT_PUBLIC_DATA_BASE); building with an empty manifest");
  return EMPTY_MANIFEST;
}
