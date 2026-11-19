// Shareable URL state (SPEC §10): ?lat&lng&z&view&preset&w=<csv>&pol&conf&inh&share.
// Parsing is tolerant (garbage -> defaults); serialising writes the position and the view always
// and other keys only when they differ from the default. Old links keep their meaning (§13.50):
// `view=` wins; a link with a position but no `view=` was written when bivariate was the default
// and still means bivariate; a bare address opens today's default. Weights,
// preset and the political pick are written in every view: they drive the place panel's bars in
// any view, so a shared link keeps them. Links from
// before §13.40 may weight `race` or carry `race=`: both are ignored (context only, never weighted).

import { MAP_MAX_ZOOM, MAP_MIN_ZOOM } from "./config";
import { CONTEXT_ONLY_IDS, DIM_ORDER } from "./dims";
import { presetById, type PolPick } from "../presets";

/** View ids are append-only, like the `w=` order: `exp` (combined exposure) came with §13.50. */
export const VIEWS = ["bivar", "heat", "humid", "rflood", "cflood", "wstress", "wb", "priorities", "exp"] as const;
export type ViewId = (typeof VIEWS)[number];

export interface AppState {
  lat: number;
  lng: number;
  z: number;
  view: ViewId;
  preset: string | null;
  weights: Record<string, number>;
  pol: PolPick;
  /** confidence hatch on */
  conf: boolean;
  /** show uninhabited hexes */
  inh: boolean;
  /** opened from a "Share this map" link: show the share card once (§10) */
  share?: boolean;
}

export const DEFAULT_STATE: AppState = { lat: 20, lng: 10, z: 2, view: "exp", preset: null, weights: {}, pol: "competitive", conf: true, inh: false };
export const MAX_WEIGHT = 5;
/** What a link without `view=` meant before §13.50, when it carries a position. */
export const LEGACY_VIEW: ViewId = "bivar";

const POLS: readonly PolPick[] = ["left", "right", "competitive"];

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
      if (order[i] && !CONTEXT_ONLY_IDS.has(order[i]) && Number.isInteger(v) && v > 0) weights[order[i]] = Math.min(MAX_WEIGHT, v);
    });
  } else if (preset) {
    Object.assign(weights, presetById(preset)!.weights);
  }
  const pre = presetById(preset);
  const positioned = p.has("lat") || p.has("lng") || p.has("z");
  return {
    lat: num(p, "lat", -85, 85, DEFAULT_STATE.lat),
    lng: num(p, "lng", -180, 180, DEFAULT_STATE.lng),
    z: num(p, "z", MAP_MIN_ZOOM, MAP_MAX_ZOOM, DEFAULT_STATE.z),
    view: oneOf(p, "view", VIEWS, positioned && !p.has("view") ? LEGACY_VIEW : DEFAULT_STATE.view),
    preset: p.has("w") ? null : preset,
    weights,
    pol: oneOf(p, "pol", POLS, pre?.pol ?? DEFAULT_STATE.pol),
    conf: p.get("conf") !== "0",
    inh: p.get("inh") === "1",
    ...(p.get("share") === "1" ? { share: true } : {}),
  };
}

export function serializeState(s: AppState, order: readonly string[] = DIM_ORDER): string {
  const p = new URLSearchParams();
  p.set("lat", s.lat.toFixed(3));
  p.set("lng", s.lng.toFixed(3));
  p.set("z", s.z.toFixed(2));
  p.set("view", s.view);
  if (s.preset) {
    p.set("preset", s.preset);
  } else {
    const csv = order.map((id) => (CONTEXT_ONLY_IDS.has(id) ? 0 : (s.weights[id] ?? 0)));
    while (csv.length && csv[csv.length - 1] === 0) csv.pop();
    if (csv.length) p.set("w", csv.join(","));
  }
  const pre = presetById(s.preset);
  if (s.pol !== (pre?.pol ?? DEFAULT_STATE.pol)) p.set("pol", s.pol);
  if (!s.conf) p.set("conf", "0");
  if (s.inh) p.set("inh", "1");
  if (s.share) p.set("share", "1");
  return p.toString();
}

export function writeUrl(s: AppState): void {
  if (typeof window === "undefined") return;
  const q = serializeState(s);
  window.history.replaceState(null, "", q ? `${window.location.pathname}?${q}` : window.location.pathname);
}
