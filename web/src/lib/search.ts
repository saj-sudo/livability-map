// Place search over the bundled gazetteer (SPEC §10; invariant 7: no request leaves the origin).
// public/gazetteer.json is built by scripts/build_gazetteer.py from Natural Earth populated
// places (public domain) and geoBoundaries ADM1 names (CC BY 4.0). Pure ranking here; the
// combobox in components/Search.tsx fetches the file lazily on first focus.

export type PlaceKind = "city" | "region";

export interface Place {
  name: string;
  /** folded search key: lowercase ASCII, no punctuation */
  key: string;
  kind: PlaceKind;
  iso2: string;
  lat: number;
  lng: number;
  /** Natural Earth population estimate for cities; null for regions */
  pop: number | null;
}

/** On-disk row: [name, key, kind ("c" | "r"), iso2, lat, lng, pop] */
export type GazetteerRow = [string, string, string, string, number, number, number | null];
export interface GazetteerFile {
  v: number;
  built: string;
  places: GazetteerRow[];
}

/** Lowercase ASCII with accents stripped and punctuation collapsed to single spaces. */
export function foldKey(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function parseGazetteer(file: GazetteerFile): Place[] {
  return (file.places ?? []).map(([name, key, kind, iso2, lat, lng, pop]) => ({
    name,
    key: key || foldKey(name),
    kind: kind === "r" ? "region" : "city",
    iso2,
    lat,
    lng,
    pop: typeof pop === "number" ? pop : null,
  }));
}

/** 4 exact, 3 prefix, 2 a later word starts with the query, 1 substring, 0 no match. */
export function matchScore(key: string, q: string): number {
  if (key === q) return 4;
  if (key.startsWith(q)) return 3;
  if (key.includes(` ${q}`)) return 2;
  if (key.includes(q)) return 1;
  return 0;
}

/** Best matches first: match strength, then cities before regions, then population, then name. */
export function rankPlaces(query: string, places: Place[], limit = 8): Place[] {
  const q = foldKey(query);
  if (!q) return [];
  const scored: { p: Place; s: number }[] = [];
  for (const p of places) {
    const s = matchScore(p.key, q);
    if (s > 0) scored.push({ p, s });
  }
  scored.sort((a, b) => b.s - a.s || (a.p.kind === b.p.kind ? 0 : a.p.kind === "city" ? -1 : 1) || (b.p.pop ?? 0) - (a.p.pop ?? 0) || a.p.name.localeCompare(b.p.name));
  return scored.slice(0, limit).map((x) => x.p);
}

/** A city is a hex or two across at zoom 6; a region needs room at zoom 5. */
export const zoomFor = (p: Place): number => (p.kind === "city" ? 6 : 5);
