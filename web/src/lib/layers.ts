// Tile layers from the manifest (SPEC §9.1, §13.32). The pipeline builds one PMTiles archive per
// resolution-plan archive (hexes.pmtiles: hex4 z2-4 + hex5 z5-7; hexes_nbhd.pmtiles: hex6 z8-9;
// hexes_city.pmtiles: hex7 z10-12, where built) and records, per layer, its H3 resolution, whether every land cell
// exists at it (`complete`) and whether it keeps drawing past its last zoom (`overzoom`). The map
// adds one source per archive and one style-layer group per tile layer, in resolution order.

import type { Manifest } from "./manifest";

export interface TileLayer {
  name: string; // source-layer name, e.g. "hex6"
  source: string; // MapLibre source id = archive name, e.g. "hexes_nbhd"
  minzoom: number;
  maxzoom: number;
  res: number;
  complete: boolean;
  overzoom: boolean;
}

// what a manifest from before the resolution plan (two layers, one archive) implies
export const DEFAULT_TILE_LAYERS: TileLayer[] = [
  { name: "hex4", source: "hexes", minzoom: 2, maxzoom: 4, res: 4, complete: true, overzoom: false },
  { name: "hex5", source: "hexes", minzoom: 5, maxzoom: 7, res: 5, complete: true, overzoom: true },
];

const resOf = (name: string): number => Number(name.replace(/\D/g, "")) || 0;

export function tileLayersFrom(tiles: Manifest["tiles"] | undefined): TileLayer[] {
  const out: TileLayer[] = [];
  for (const [source, archive] of Object.entries(tiles ?? {})) {
    for (const l of archive?.layers ?? []) {
      out.push({ name: l.name, source, minzoom: l.minzoom, maxzoom: l.maxzoom, res: l.res ?? resOf(l.name), complete: l.complete ?? true, overzoom: l.overzoom ?? false });
    }
  }
  if (!out.length) return DEFAULT_TILE_LAYERS;
  out.sort((a, b) => a.res - b.res);
  // older manifests carry no flags: their top layer is the one that overzooms
  if (!out.some((l) => l.overzoom)) out[out.length - 1] = { ...out[out.length - 1], overzoom: true };
  return out;
}

/** One vector source per archive: the MapLibre source id is the archive name. */
export const archivesFrom = (tiles: Manifest["tiles"] | undefined): { id: string; key: string }[] =>
  Object.entries(tiles ?? {}).map(([id, a]) => ({ id, key: a.key }));
