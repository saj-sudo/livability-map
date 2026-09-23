// Pure "describe a hex" logic for the inspector (SPEC §10), unit-testable without React.
// Reads tile attributes (SPEC §6.1) and never turns a missing value into 0 (invariant 3).

import type { ClientManifest, ClientSource } from "./clientManifest";
import { HAZARD_IDS, HAZARD_RAW, type DimInfo } from "./dims";
import { formatDimRaw, formatHazardRaw, formatPopulation } from "./format";
import { BIVAR_WORDS } from "./palette";

export type Props = Record<string, unknown>;

export interface HazardRow {
  id: string;
  name: string;
  raw: string | null; // formatted raw value with unit, null when missing
  score: number | null;
  ok: boolean;
}

export interface LifeRow {
  id: string;
  name: string;
  kind: DimInfo["kind"];
  value: string | null; // formatted value, null = no data here
  score: number | null;
  res: string; // admin1 | county | tract | national | none
  chip: string;
  shares?: { key: string; label: string; pct: number }[];
  majority?: string;
}

export interface HexModel {
  title: string;
  subtitle: string;
  population: string;
  resolution: string;
  inhabited: boolean;
  hazards: HazardRow[];
  coverage: string;
  exposure: number | null;
  /** number of hazard layers with data, 0-4 */
  coverageN: number;
  wellbeing: { value: string | null; score: number | null; source: string; res: string };
  bivar: string;
  /** bivariate class 1-9, 0 when unclassified */
  bivarClass: number;
  /** present-day environment (group `env`): shown beside the hazards, never part of exposure */
  env: LifeRow[];
  life: LifeRow[];
  sources: ClientSource[];
}

const RACE_LABELS: Record<string, string> = { w: "white", b: "Black", h: "Hispanic or Latino", a: "Asian / Pacific Islander", o: "other" };

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : null);

export function countryName(iso2: string | null): string {
  if (!iso2) return "no country";
  try {
    const dn = new Intl.DisplayNames(["en"], { type: "region" });
    const name = dn.of(iso2) ?? iso2;
    return /^pseudo/i.test(name) ? iso2 : name; // user-assigned codes (fixtures) map to "Pseudo-*" locales
  } catch {
    return iso2;
  }
}

// average H3 cell area per resolution (km², h3 v4), for the inspector's resolution line
const HEX_AREA: Record<number, string> = { 4: "1,770", 5: "253", 6: "36", 7: "5.2", 8: "0.74", 9: "0.11", 10: "0.015" };
const resolutionLabel = (r: number): string => `H3 res ${r} hex (~${HEX_AREA[r] ?? "?"} km²)`;

export function describeHex(p: Props, sourceLayer: string, dims: DimInfo[], manifest: ClientManifest): HexModel {
  const iso = str(p.iso_a2);
  const admin1 = str(p.admin1_name);
  const pop = num(p.population);
  const inhabited = p.inhabited === true;
  const hazards: HazardRow[] = HAZARD_IDS.map((id) => {
    const raw = num(p[HAZARD_RAW[id].attr]);
    const ok = p[`${id}_ok`] === true;
    const dim = dims.find((d) => d.id === id);
    return { id, name: dim?.name ?? id, raw: ok ? formatHazardRaw(id, raw) : id === "wstress" && raw === -1 ? formatHazardRaw(id, raw) : null, score: ok ? num(p[`${id}_score`]) : null, ok };
  });
  const coverageN = num(p.coverage) ?? hazards.filter((h) => h.ok).length;
  const wbSource = str(p.wb_source) ?? "none";
  const wbValue = num(p.wb_value);
  const wellbeing = {
    value: wbValue === null ? null : wbSource === "shdi" ? `Subnational HDI ${wbValue.toFixed(3)}` : wbSource === "whr" ? `life evaluation ${wbValue.toFixed(2)} / 10` : wbValue.toFixed(3),
    score: num(p.wb_score),
    source: wbSource,
    res: str(p.wb_res) ?? "none",
  };
  const bivar = num(p.bivar) ?? 0;
  const rowFor = (d: DimInfo): LifeRow => {
      const res = str(p[`${d.id}_res`]) ?? "none";
      const row: LifeRow = { id: d.id, name: d.name, kind: d.kind, value: null, score: null, res, chip: d.chip };
      if (res === "none") return row;
      if (d.kind === "score") {
        row.value = formatDimRaw(d, num(p[`${d.id}_raw`]), res);
        row.score = num(p[`${d.id}_score`]);
      } else if (d.kind === "signed") {
        const lean = num(p[`${d.id}_lean`]);
        row.value = lean === null ? null : lean >= 0 ? `D+${Math.round(lean)} (two-party margin)` : `R+${Math.round(-lean)} (two-party margin)`;
      } else {
        row.shares = ["w", "b", "h", "a", "o"].map((k) => ({ key: k, label: RACE_LABELS[k], pct: num(p[`${d.id}_${k}`]) ?? 0 }));
        const maj = str(p[`${d.id}_maj`]);
        row.majority = maj && maj !== "none" ? RACE_LABELS[maj] : undefined;
        row.value = row.majority ? `largest group: ${row.majority}` : "shares below";
      }
      return row;
  };
  const life: LifeRow[] = dims.filter((d) => d.group === "life").map(rowFor);
  const env: LifeRow[] = dims.filter((d) => d.group === "env").map(rowFor);
  const usedIds = new Set<string>(["natural_earth_land", "geoboundaries_adm0", "geoboundaries_adm1", "ghsl_pop"]);
  for (const h of hazards) if (h.ok) for (const s of manifest.dimensionSources[h.id] ?? []) usedIds.add(s);
  if (wbSource === "shdi") ["gdl_shdi", "gdl_shdi_regions"].forEach((s) => usedIds.add(s));
  if (wbSource === "whr") usedIds.add("whr_ladder");
  for (const row of [...env, ...life]) if (row.res !== "none") for (const s of manifest.dimensionSources[row.id] ?? []) usedIds.add(s);
  return {
    title: admin1 ?? countryName(iso),
    subtitle: admin1 ? countryName(iso) : "",
    population: formatPopulation(pop),
    resolution: resolutionLabel(num(p.res) ?? (Number(sourceLayer.replace(/\D/g, "")) || 4)),
    inhabited,
    hazards,
    coverage: `${coverageN} of 4 hazard layers`,
    exposure: num(p.exposure),
    coverageN,
    wellbeing,
    bivar: BIVAR_WORDS[bivar] ?? BIVAR_WORDS[0],
    bivarClass: BIVAR_WORDS[bivar] ? bivar : 0,
    env,
    life,
    sources: manifest.sources.filter((s) => usedIds.has(s.id)),
  };
}
