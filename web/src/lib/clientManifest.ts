// The slice of manifest.json that ships to the browser (embedded in the static HTML): enough
// for the inspector's sources list, the scenario label and the coverage chips. /methodology
// renders the full manifest server-side at build time.

import type { Manifest, ManifestSource } from "./manifest";

export interface ClientSource {
  id: string;
  name: string;
  vintage: string;
  license: string;
  license_note: string;
  attribution: string;
  processing: string;
  url: string | null;
}

export interface ClientManifest {
  built_at: string | null;
  scenario: string;
  horizon: string;
  non_commercial: boolean;
  fixtures?: boolean;
  tiles: Manifest["tiles"];
  sources: ClientSource[];
  /** dimension id -> source ids behind it */
  dimensionSources: Record<string, string[]>;
  /** dimension id -> note from the registry */
  notes: Record<string, string>;
}

const pickSource = (s: ManifestSource): ClientSource => ({
  id: s.id,
  name: s.name,
  vintage: s.vintage,
  license: s.license,
  license_note: s.license_note,
  attribution: s.attribution,
  processing: s.processing,
  url: s.url,
});

export function toClientManifest(m: Manifest): ClientManifest {
  const dims = [...(m.hazards ?? []), ...(m.dimensions ?? [])];
  return {
    built_at: m.built_at,
    scenario: m.scenario,
    horizon: m.horizon,
    non_commercial: m.non_commercial,
    fixtures: m.fixtures,
    tiles: m.tiles ?? {},
    sources: (m.sources ?? []).map(pickSource),
    dimensionSources: Object.fromEntries(dims.map((d) => [d.id, d.sources ?? []])),
    notes: Object.fromEntries(dims.map((d) => [d.id, d.note ?? ""])),
  };
}

export const SCENARIO_LABELS: Record<string, string> = {
  rcp45_ssp245: "moderate pathway (RCP4.5 / SSP2-4.5)",
};
