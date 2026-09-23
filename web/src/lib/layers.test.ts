import { describe, expect, it } from "vitest";
import { archivesFrom, DEFAULT_TILE_LAYERS, tileLayersFrom } from "./layers";
import type { Manifest } from "./manifest";

export const TILES: Manifest["tiles"] = {
  hexes: { key: "hexes.pmtiles", sha256: "", bytes: 1, minzoom: 2, maxzoom: 7, layers: [
    { name: "hex4", minzoom: 2, maxzoom: 4, res: 4, complete: true, overzoom: false },
    { name: "hex5", minzoom: 5, maxzoom: 7, res: 5, complete: true, overzoom: true },
  ] },
  hexes_fine: { key: "hexes_fine.pmtiles", sha256: "", bytes: 1, minzoom: 8, maxzoom: 13, layers: [
    { name: "hex7", minzoom: 10, maxzoom: 13, res: 7, complete: false, overzoom: true },
    { name: "hex6", minzoom: 8, maxzoom: 9, res: 6, complete: false, overzoom: true },
  ] },
};

describe("tile layers from the manifest (SPEC §9.1)", () => {
  it("orders layers by resolution across archives and keeps their source", () => {
    const L = tileLayersFrom(TILES);
    expect(L.map((l) => l.name)).toEqual(["hex4", "hex5", "hex6", "hex7"]);
    expect(L[2]).toMatchObject({ source: "hexes_fine", res: 6, complete: false, overzoom: true });
    expect(archivesFrom(TILES)).toEqual([{ id: "hexes", key: "hexes.pmtiles" }, { id: "hexes_fine", key: "hexes_fine.pmtiles" }]);
  });

  it("falls back to hex4/hex5 for a manifest from before the resolution plan", () => {
    const L = tileLayersFrom({ hexes: { key: "hexes.pmtiles", sha256: "", bytes: 1, minzoom: 2, maxzoom: 7, layers: [{ name: "hex4", minzoom: 2, maxzoom: 4 }, { name: "hex5", minzoom: 5, maxzoom: 7 }] } });
    expect(L[0]).toMatchObject({ res: 4, complete: true, overzoom: false, source: "hexes" });
    expect(L[1]).toMatchObject({ res: 5, complete: true, overzoom: true, source: "hexes" });
    expect(tileLayersFrom(undefined)).toEqual(DEFAULT_TILE_LAYERS);
    expect(tileLayersFrom({})).toEqual(DEFAULT_TILE_LAYERS);
  });
});
