// Where the app reads its data (SPEC §5, §13.24). In development `publish --target local`
// copies hexes.pmtiles + manifest.json into public/data (same origin); in production
// NEXT_PUBLIC_DATA_BASE points at the R2 custom domain and is inlined at build time.
export const DATA_BASE = (process.env.NEXT_PUBLIC_DATA_BASE ?? "/data").replace(/\/$/, "");
export const MANIFEST_URL = `${DATA_BASE}/manifest.json`;
export const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/positron"; // SPEC §9.4, §13.5
export const BASEMAP_ATTRIBUTION = "OpenFreeMap © OpenMapTiles Data from OpenStreetMap";

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
