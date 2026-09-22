// Shareable URL state (SPEC §10): ?lat&lng&z&view&preset&w=<csv>&pol&race&conf&inh.
// Parsing is tolerant (garbage -> defaults); serialising writes only non-default keys.

import { DIM_ORDER } from "./dims";
import { presetById, type PolPick, type RacePick } from "../presets";

export const VIEWS = ["bivar", "heat", "rflood", "cflood", "wstress", "wb", "priorities"] as const;
export type ViewId = (typeof VIEWS)[number];

export interface AppState {
  lat: number;
  lng: number;
  z: number;
  view: ViewId;
  preset: string | null;
  weights: Record<string, number>;
  pol: PolPick;
  race: RacePick;
  /** confidence hatch on */
  conf: boolean;
  /** show uninhabited hexes */
  inh: boolean;
}

export const DEFAULT_STATE: AppState = { lat: 20, lng: 10, z: 2, view: "bivar", preset: null, weights: {}, pol: "competitive", race: "diverse", conf: true, inh: false };
export const MAX_WEIGHT = 5;

const POLS: readonly PolPick[] = ["left", "right", "competitive"];
const RACES: readonly RacePick[] = ["w", "b", "h", "a", "o", "diverse"];

function num(p: URLSearchParams, key: string, lo: number, hi: number, dflt: number): number {
  if (!p.has(key)) return dflt;
  const v = Number(p.get(key));
  return Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : dflt;
}

function oneOf<T extends string>(p: URLSearchParams, key: string, all: readonly T[], dflt: T): T {
  const v = p.get(key);
  return v !== null && (all as readonly string[]).includes(v) ? (v as T) : dflt;
}

export function parseState(search: string, order: readonly string[] = DIM_ORDER): AppState {
  const p = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const preset = presetById(p.get("preset"))?.id ?? null;
  const weights: Record<string, number> = {};
  if (p.has("w")) {
    p.get("w")!.split(",").forEach((tok, i) => {
      const v = parseInt(tok, 10);
      if (order[i] && Number.isInteger(v) && v > 0) weights[order[i]] = Math.min(MAX_WEIGHT, v);
    });
  } else if (preset) {
    Object.assign(weights, presetById(preset)!.weights);
  }
  const pre = presetById(preset);
  return {
    lat: num(p, "lat", -85, 85, DEFAULT_STATE.lat),
    lng: num(p, "lng", -180, 180, DEFAULT_STATE.lng),
    z: num(p, "z", 1, 14, DEFAULT_STATE.z),
    view: oneOf(p, "view", VIEWS, DEFAULT_STATE.view),
    preset: p.has("w") ? null : preset,
    weights,
    pol: oneOf(p, "pol", POLS, pre?.pol ?? DEFAULT_STATE.pol),
    race: oneOf(p, "race", RACES, pre?.race ?? DEFAULT_STATE.race),
    conf: p.get("conf") !== "0",
    inh: p.get("inh") === "1",
  };
}

export function serializeState(s: AppState, order: readonly string[] = DIM_ORDER): string {
  const p = new URLSearchParams();
  p.set("lat", s.lat.toFixed(3));
  p.set("lng", s.lng.toFixed(3));
  p.set("z", s.z.toFixed(2));
  if (s.view !== DEFAULT_STATE.view) p.set("view", s.view);
  if (s.view === "priorities") {
    if (s.preset) {
      p.set("preset", s.preset);
    } else {
      const csv = order.map((id) => s.weights[id] ?? 0);
      while (csv.length && csv[csv.length - 1] === 0) csv.pop();
      if (csv.length) p.set("w", csv.join(","));
    }
    const pre = presetById(s.preset);
    if (s.pol !== (pre?.pol ?? DEFAULT_STATE.pol)) p.set("pol", s.pol);
    if (s.race !== (pre?.race ?? DEFAULT_STATE.race)) p.set("race", s.race);
  }
  if (!s.conf) p.set("conf", "0");
  if (s.inh) p.set("inh", "1");
  return p.toString();
}

export function writeUrl(s: AppState): void {
  if (typeof window === "undefined") return;
  const q = serializeState(s);
  window.history.replaceState(null, "", q ? `${window.location.pathname}?${q}` : window.location.pathname);
}
