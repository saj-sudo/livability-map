// Where the app reads its data (SPEC §5, §13.24). In development `publish --target local`
// copies hexes.pmtiles + manifest.json into public/data (same origin); in production
// NEXT_PUBLIC_DATA_BASE points at the R2 custom domain and is inlined at build time.
export const DATA_BASE = (process.env.NEXT_PUBLIC_DATA_BASE ?? "/data").replace(/\/$/, "");
export const MANIFEST_URL = `${DATA_BASE}/manifest.json`;

// Basemap (SPEC §9.4, §13.5): OpenFreeMap, no key, no signup. One style per theme (§13.10).
export const BASEMAP_STYLES = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
} as const;
export const BASEMAP_STYLE = BASEMAP_STYLES.light;
export const BASEMAP_ATTRIBUTION = "OpenFreeMap © OpenMapTiles Data from OpenStreetMap";

// The bundled place-name index for search (same origin, fetched lazily on first focus).
export const GAZETTEER_URL = "/gazetteer.json";

// hex4 tiles are slim (no raw values) below this zoom and hexes are ~2 px, so the inspector
// asks the person to zoom in (SPEC §9.2, decision §13.18).
export const INSPECT_MIN_ZOOM = 3;
// hex4 layers stop and hex5 layers start here (SPEC §9.1)
export const HEX_SPLIT_ZOOM = 5;
export const MAP_MIN_ZOOM = 2;
export const MAP_MAX_ZOOM = 12;

export function tilesUrl(key: string): string {
  // absolute pmtiles URLs are required by the pmtiles protocol; relative bases resolve at runtime
  if (typeof window !== "undefined" && !/^https?:/.test(DATA_BASE)) {
    return `${window.location.origin}${DATA_BASE}/${key}`;
  }
  return `${DATA_BASE}/${key}`;
}
