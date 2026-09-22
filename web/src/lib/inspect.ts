// Pure "describe a hex" logic for the inspector (SPEC §10), unit-testable without React.
// Reads tile attributes (SPEC §6.1) and never turns a missing value into 0 (invariant 3).

import type { ClientManifest, ClientSource } from "./clientManifest";
import { HAZARD_IDS, HAZARD_RAW, type DimInfo } from "./dims";
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
  wellbeing: { value: string | null; score: number | null; source: string; res: string };
  bivar: string;
  life: LifeRow[];
  sources: ClientSource[];
}

const RACE_LABELS: Record<string, string> = { w: "white", b: "Black", h: "Hispanic or Latino", a: "Asian / Pacific Islander", o: "other" };
const WSTRESS_LABELS: Record<number, string> = { [-1]: "arid and low water use (not scored)", 0: "low", 1: "low to medium", 2: "medium to high", 3: "high", 4: "extremely high" };

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : null);

export function countryName(iso2: string | null): string {
  if (!iso2) return "no country";
  try {
    const dn = new Intl.DisplayNames(["en"], { type: "region" });
    return dn.of(iso2) ?? iso2;
  } catch {
    return iso2;
  }
}

function fmtRaw(id: string, v: number | null): string | null {
  if (v === null) return null;
  if (id === "heat") return `${Math.round(v)} days/yr`;
  if (id === "rflood" || id === "cflood") return `${(100 * v).toFixed(1)}% of area`;
  if (id === "wstress") return WSTRESS_LABELS[v] ?? String(v);
  return String(v);
}

function fmtLife(d: DimInfo, raw: number | null): string | null {
  if (raw === null) return null;
  switch (d.id) {
    case "jobs":
      return raw <= 10 ? `${raw.toFixed(1)} / 10 (OECD score)` : raw <= 1 ? `${(100 * raw).toFixed(0)}% employed` : `${raw.toFixed(0)}% employed`;
    case "transit":
      return `${raw.toFixed(1)} transit trips/hour nearby`;
    case "school":
      return `${raw.toFixed(0)}% graduate on time`;
    case "lgbtq":
      return `${raw.toFixed(1)} same-sex couples per 1,000 households`;
    case "incmix":
      return raw <= 1 ? `${raw.toFixed(2)}` : `${raw.toFixed(2)}`;
    case "house":
      return raw <= 10 ? `${raw.toFixed(1)} / 10 (OECD, higher = worse)` : `${raw.toFixed(0)}% of income on rent`;
    case "health":
      return raw <= 10 ? `${raw.toFixed(1)} / 10 (OECD score)` : `${raw.toFixed(1)} physicians per 10,000`;
    default:
      return String(raw);
  }
}

export function describeHex(p: Props, sourceLayer: string, dims: DimInfo[], manifest: ClientManifest): HexModel {
  const iso = str(p.iso_a2);
  const admin1 = str(p.admin1_name);
  const pop = num(p.population);
  const inhabited = p.inhabited === true;
  const hazards: HazardRow[] = HAZARD_IDS.map((id) => {
    const raw = num(p[HAZARD_RAW[id].attr]);
    const ok = p[`${id}_ok`] === true;
    const dim = dims.find((d) => d.id === id);
    return { id, name: dim?.name ?? id, raw: ok ? fmtRaw(id, raw) : id === "wstress" && raw === -1 ? fmtRaw(id, raw) : null, score: ok ? num(p[`${id}_score`]) : null, ok };
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
  const life: LifeRow[] = dims
    .filter((d) => d.group === "life")
    .map((d) => {
      const res = str(p[`${d.id}_res`]) ?? "none";
      const row: LifeRow = { id: d.id, name: d.name, kind: d.kind, value: null, score: null, res, chip: d.chip };
      if (res === "none") return row;
      if (d.kind === "score") {
        row.value = fmtLife(d, num(p[`${d.id}_raw`]));
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
    });
  const usedIds = new Set<string>(["natural_earth_land", "geoboundaries_adm0", "geoboundaries_adm1", "ghsl_pop"]);
  for (const h of hazards) if (h.ok) for (const s of manifest.dimensionSources[h.id] ?? []) usedIds.add(s);
  if (wbSource === "shdi") ["gdl_shdi", "gdl_shdi_regions"].forEach((s) => usedIds.add(s));
  if (wbSource === "whr") usedIds.add("whr_ladder");
  for (const row of life) if (row.res !== "none") for (const s of manifest.dimensionSources[row.id] ?? []) usedIds.add(s);
  return {
    title: admin1 ?? countryName(iso),
    subtitle: admin1 ? countryName(iso) : "",
    population: pop === null ? "population unknown" : `${pop.toLocaleString("en-US")} people`,
    resolution: sourceLayer === "hex5" ? "H3 res 5 hex (~253 km²)" : "H3 res 4 hex (~1,770 km²)",
    inhabited,
    hazards,
    coverage: `${coverageN} of 4 hazard layers`,
    exposure: num(p.exposure),
    wellbeing,
    bivar: BIVAR_WORDS[bivar] ?? BIVAR_WORDS[0],
    life,
    sources: manifest.sources.filter((s) => usedIds.has(s.id)),
  };
}
