// What the map does when something it depends on fails (SPEC §10, decision §13.40). Pure, so
// vitest covers it; MapView wires it to MapLibre events and MapApp shows the result.
//
// - No WebGL 2: MapLibre cannot draw at all, so the page says so instead of a blank canvas.
// - Basemap down (OpenFreeMap style, tiles, glyphs or sprites): the hexes still draw, on a plain
//   background style, and a notice says the background is missing. The data never waits on it.
// - Tile archive unreachable: a notice that stays until the page is reloaded, naming the archive.

import type { StyleSpecification } from "maplibre-gl";
import { BASEMAP_STYLES } from "./config";
import type { Theme } from "./theme";

/** How long the basemap style may take before the map switches to the plain background. */
export const STYLE_TIMEOUT_MS = 8000;

export const BASEMAP_HOSTS: readonly string[] = [...new Set(Object.values(BASEMAP_STYLES).map((u) => new URL(u).host))];

interface CanvasLike {
  getContext(kind: string): unknown;
}

/** True when the browser can give MapLibre a WebGL 2 context. */
export function supportsWebGL2(create: () => CanvasLike | null = () => document.createElement("canvas")): boolean {
  try {
    return Boolean(create()?.getContext("webgl2"));
  } catch {
    return false;
  }
}

/** A style with no external request: the hex layers draw on a flat background. */
export function fallbackStyle(theme: Theme): StyleSpecification {
  return {
    version: 8,
    name: "plain background (basemap unavailable)",
    sources: {},
    layers: [{ id: "background", type: "background", paint: { "background-color": theme === "dark" ? "#1c1f24" : "#eceae4" } }],
  };
}

export interface MapProblems {
  basemap: boolean;
  /** archive ids whose tiles failed to load */
  tiles: string[];
}

export const NO_PROBLEMS: MapProblems = { basemap: false, tiles: [] };

export type ErrorKind = { kind: "basemap" } | { kind: "tiles"; archive: string } | { kind: "other" };

interface MapErrorLike {
  sourceId?: string;
  error?: { message?: string; url?: string } | null;
}

/** Which dependency a MapLibre `error` event is about. */
export function classifyError(e: MapErrorLike, archiveIds: readonly string[], hosts: readonly string[] = BASEMAP_HOSTS): ErrorKind {
  if (e.sourceId && archiveIds.includes(e.sourceId)) return { kind: "tiles", archive: e.sourceId };
  if (e.sourceId) return { kind: "basemap" }; // any other source belongs to the basemap style
  const where = `${e.error?.url ?? ""} ${e.error?.message ?? ""}`;
  if (hosts.some((h) => where.includes(h))) return { kind: "basemap" };
  return { kind: "other" };
}

/** Fold one error into the problem set; the same object back when nothing changed. */
export function noteProblem(p: MapProblems, k: ErrorKind): MapProblems {
  if (k.kind === "basemap") return p.basemap ? p : { ...p, basemap: true };
  if (k.kind === "tiles") return p.tiles.includes(k.archive) ? p : { ...p, tiles: [...p.tiles, k.archive] };
  return p;
}

/** The persistent notice for the current problems, most serious first; null when all is well. */
export function problemMessage(p: MapProblems): string | null {
  if (p.tiles.length) {
    return `The map data could not be loaded (${p.tiles.join(", ")}), so some or all hexagons are missing. Reloading may help; if it keeps happening, the data host is down.`;
  }
  if (p.basemap) return "The background map is unavailable right now. The data is shown on a plain background.";
  return null;
}
