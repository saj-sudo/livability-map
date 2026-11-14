// Pure "describe a hex" logic for the inspector (SPEC §10), unit-testable without React.
// Reads tile attributes (SPEC §6.1) and never turns a missing value into 0 (invariant 3).

import type { ClientManifest, ClientSource } from "./clientManifest";
import { HAZARD_IDS, HAZARD_RAW, type DimInfo } from "./dims";
import { formatDimRaw, formatHazardRaw, formatPopulation } from "./format";
import { BIVAR_WORDS } from "./palette";

export type Props = Record<string, unknown>;

/** What a score is (SPEC §16 Next steps): shown in the place panel and on /methodology. */
export const SCORE_MEANING =
  "Scores out of 100 are ranks among inhabited places at this map scale (a percentile): 75 means higher than 75% of them. A rank is not an absolute risk level.";

/** The note above the first scores in the place panel: with priorities set, the match is named
 *  first so it is not mistaken for a rank (the same place can show a match of 75 and a rank of 25). */
export function scoreNoteFor(hasPriorities: boolean): string {
  if (!hasPriorities) return SCORE_MEANING;
  return "Your priorities show a match from 0 to 100: how well this place fits what you weighted. The other scores are ranks among inhabited places at this map scale (75 means higher than 75% of them), not an absolute risk level.";
}

/** What the combined exposure number is (SPEC §8.3): shown beside it in the panel and in compare. */
export const EXPOSURE_MEANING = "the average of the hazard ranks present";

/** Why the heat layer understates humid heat: shown on the heat row and on /methodology. */
export const HEAT_CAVEAT =
  "Counts dry-air days above 35 °C and ignores humidity, so humid places (Bangladesh, the US Gulf coast, West Africa, Southeast Asia) can look milder here than their real heat stress. The humid-heat row covers humidity; read the two together.";

/** What the humid-heat layer adds, and that heat counts twice (SPEC §13.47): shown on its row and on /methodology. */
export const HUMID_NOTE =
  "Counts days when the heat index (temperature and humidity together) passes 35 °C. It sits beside dry heat rather than replacing it, so heat counts twice in combined exposure.";

export interface HazardRow {
  id: string;
  name: string;
  raw: string | null; // formatted raw value with unit, null when missing
  score: number | null;
  ok: boolean;
  /** a caveat shown under the row (heat: humidity is not counted; humid heat: heat counts twice) */
  note?: string;
}

export interface LifeRow {
  id: string;
  name: string;
  kind: DimInfo["kind"];
  value: string | null; // formatted value, null = no data here
  score: number | null;
  res: string; // a resolution tag: hex | grid | basin | tract | area | city | county | admin1 | national | none
  chip: string;
  /** the dimension's direction: a high score is bad news when more of it is worse */
  higherIs: DimInfo["higher_is"];
  shares?: { key: string; label: string; pct: number }[];
  majority?: string;
}

export interface HexModel {
  title: string;
  subtitle: string;
  population: string;
  /** the count behind `population`, null when unknown (never 0 for missing) */
  populationN: number | null;
  /** technical label ("H3 res 4 hex (~1,770 km²)"), for a tooltip only */
  resolution: string;
  /** H3 resolution of the hex */
  res: number;
  /** average area of a hex at this resolution, e.g. "1,770", null when unknown */
  areaKm2: string | null;
  inhabited: boolean;
  hazards: HazardRow[];
  coverage: string;
  /** what the scores mean (ranks, not absolute risk) */
  scoreNote: string;
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
export const hexAreaKm2 = (r: number): string | null => HEX_AREA[r] ?? null;

export function describeHex(p: Props, sourceLayer: string, dims: DimInfo[], manifest: ClientManifest): HexModel {
  const iso = str(p.iso_a2);
  const admin1 = str(p.admin1_name);
  const pop = num(p.population);
  const inhabited = p.inhabited === true;
  const hazards: HazardRow[] = HAZARD_IDS.map((id) => {
    const raw = num(p[HAZARD_RAW[id].attr]);
    const ok = p[`${id}_ok`] === true;
    const dim = dims.find((d) => d.id === id);
    const row: HazardRow = { id, name: dim?.name ?? id, raw: ok ? formatHazardRaw(id, raw) : id === "wstress" && raw === -1 ? formatHazardRaw(id, raw) : null, score: ok ? num(p[`${id}_score`]) : null, ok };
    if (id === "heat") row.note = HEAT_CAVEAT;
    if (id === "humid") row.note = HUMID_NOTE;
    return row;
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
      const row: LifeRow = { id: d.id, name: d.name, kind: d.kind, value: null, score: null, res, chip: d.chip, higherIs: d.higher_is };
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
  const hexRes = num(p.res) ?? (Number(sourceLayer.replace(/\D/g, "")) || 4);
  const usedIds = new Set<string>(["natural_earth_land", "geoboundaries_adm0", "geoboundaries_adm1", "ghsl_pop"]);
  for (const h of hazards) if (h.ok) for (const s of manifest.dimensionSources[h.id] ?? []) usedIds.add(s);
  if (wbSource === "shdi") ["gdl_shdi", "gdl_shdi_regions"].forEach((s) => usedIds.add(s));
  if (wbSource === "whr") usedIds.add("whr_ladder");
  for (const row of [...env, ...life]) if (row.res !== "none") for (const s of manifest.dimensionSources[row.id] ?? []) usedIds.add(s);
  return {
    title: admin1 ?? countryName(iso),
    subtitle: admin1 ? countryName(iso) : "",
    population: formatPopulation(pop),
    populationN: pop,
    resolution: resolutionLabel(hexRes),
    res: hexRes,
    areaKm2: hexAreaKm2(hexRes),
    inhabited,
    hazards,
    coverage: `${coverageN} of ${HAZARD_IDS.length} hazard layers`,
    scoreNote: SCORE_MEANING,
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
