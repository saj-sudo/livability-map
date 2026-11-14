// Which places are selected (SPEC §10): place A in the inspector, place B while comparing, and
// whether the person is picking B. Pure, so every transition is covered by vitest; MapApp holds
// the state and MapView draws the outlines from it (one source of truth for panel and map).

/** Anything with an H3 id; MapView's SelectedHex in the app, plain objects in tests. */
export interface HexRef {
  h3: string;
}

export interface Selection<H extends HexRef> {
  a: H | null;
  b: H | null;
  /** waiting for the person to pick a second place */
  picking: boolean;
}

/** The banner shown while the person picks place B. */
export const PICK_BANNER = "Pick a second place on the map, or search for one.";

export const EMPTY_SELECTION: Selection<never> = { a: null, b: null, picking: false };

export type SelectionAction<H extends HexRef> =
  /** a map click or a search landing; null = nothing there (sea, an empty spot) */
  | { type: "select"; hex: H | null }
  | { type: "startPicking" }
  | { type: "cancelPicking" }
  | { type: "swap" }
  /** close the comparison, keep place A */
  | { type: "closeCompare" }
  /** close the place panel altogether */
  | { type: "close" }
  /** Escape: the innermost thing first (picking, then the comparison, then the panel) */
  | { type: "escape" };

export function selectionReducer<H extends HexRef>(s: Selection<H>, action: SelectionAction<H>): Selection<H> {
  switch (action.type) {
    case "select": {
      const hex = action.hex;
      if (s.picking) {
        // while picking, an empty click does nothing (place A stays), and A itself is not B
        if (!hex || hex.h3 === s.a?.h3) return s;
        return { a: s.a, b: hex, picking: false };
      }
      if (!hex) return { a: null, b: null, picking: false };
      // a new A keeps an open comparison unless it is the same place as B
      return { a: hex, b: s.b && s.b.h3 !== hex.h3 ? s.b : null, picking: false };
    }
    case "startPicking":
      return s.a ? { ...s, picking: true } : s;
    case "cancelPicking":
      return s.picking ? { ...s, picking: false } : s;
    case "swap":
      return s.a && s.b ? { a: s.b, b: s.a, picking: false } : s;
    case "closeCompare":
      return s.b || s.picking ? { a: s.a, b: null, picking: false } : s;
    case "close":
      return s.a || s.b || s.picking ? { a: null, b: null, picking: false } : s;
    case "escape":
      if (s.picking) return { ...s, picking: false };
      if (s.b) return { ...s, b: null };
      if (s.a) return { a: null, b: null, picking: false };
      return s;
  }
}

/** The places that should carry an outline on the map, A first. */
export function selectedIds<H extends HexRef>(s: Selection<H>): string[] {
  return [s.a?.h3, s.b?.h3].filter((x): x is string => Boolean(x));
}

/** Where an outline was drawn: a hex can live in several sources and source layers. */
export interface OutlineKey {
  source: string;
  sourceLayer: string;
  id: string;
}

const keyOf = (k: OutlineKey) => `${k.source}\u0000${k.sourceLayer}\u0000${k.id}`;

/** Outlines to clear and to set to go from `prev` to `next`. */
export function diffOutlines(prev: readonly OutlineKey[], next: readonly OutlineKey[]): { clear: OutlineKey[]; set: OutlineKey[] } {
  const p = new Set(prev.map(keyOf));
  const n = new Set(next.map(keyOf));
  return { clear: prev.filter((k) => !n.has(keyOf(k))), set: next.filter((k) => !p.has(keyOf(k))) };
}
