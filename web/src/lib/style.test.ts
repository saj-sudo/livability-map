import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { hatchImage } from "./hatch";
import { TILES } from "./layers.test";
import { tileLayersFrom } from "./layers";
import { buildLayers, fillLayerIds, isHexLayerId, layerId, mergeStyleOnThemeChange, SOURCE_ID } from "./style";

const dim = (id: string, group: DimInfo["group"], higher_is: DimInfo["higher_is"] = "better"): DimInfo => ({ id, name: id, group, kind: "score", higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "hazard", "worse"), dim("wb", "wellbeing"), dim("jobs", "life")];
const LAYERS = tileLayersFrom({ hexes: { key: "hexes.pmtiles", sha256: "", bytes: 1, minzoom: 2, maxzoom: 7, layers: [{ name: "hex4", minzoom: 2, maxzoom: 4 }, { name: "hex5", minzoom: 5, maxzoom: 7 }] } });
const PICKS = { pol: "competitive", race: "diverse" } as const;
const KINDS = ["fill", "hatch", "national", "hover", "halo", "selected"];

function styleWith(layers: ReturnType<typeof buildLayers>): StyleSpecification {
  const vector = { type: "vector" as const, tiles: ["https://example.org/{z}/{x}/{y}.pbf"] };
  return { version: 8 as const, sources: { [SOURCE_ID]: vector, hexes_fine: vector }, layers };
}

describe("layer stack (SPEC §9.3)", () => {
  it("is a valid MapLibre style for every view and both themes", () => {
    for (const theme of ["light", "dark"] as const) {
      for (const view of ["bivar", "heat", "wb", "priorities"] as const) {
        const layers = buildLayers({ view, dims: DIMS, weights: { heat: 2, jobs: 1 }, picks: PICKS, theme }, false, true, LAYERS);
        const errors = validateStyleMin(styleWith(layers) as never);
        expect(errors.map((e) => e.message)).toEqual([]);
        expect(layers.map((l) => l.id)).toEqual([...KINDS.map((k) => `${k}-hex4`), ...KINDS.map((k) => `${k}-hex5`)]);
      }
    }
  });

  it("uses exclusive maxzoom below the top layer and overzooms the top layer", () => {
    const layers = buildLayers({ view: "bivar", dims: DIMS, weights: {}, picks: PICKS }, false, true, LAYERS);
    const fill4 = layers.find((l) => l.id === layerId("fill", "hex4"))!;
    const fill5 = layers.find((l) => l.id === layerId("fill", "hex5"))!;
    expect(fill4.minzoom).toBe(2);
    expect(fill4.maxzoom).toBe(5);
    expect(fill5.minzoom).toBe(5);
    expect(fill5.maxzoom).toBeUndefined();
    expect(fillLayerIds(LAYERS)).toEqual(["fill-hex4", "fill-hex5"]);
  });

  it("overzooms per manifest flag and hides refined parents from the next layer's minzoom", () => {
    const layers = buildLayers({ view: "bivar", dims: DIMS, weights: {}, picks: PICKS }, false, true, tileLayersFrom(TILES));
    const get = (id: string) => layers.find((l) => l.id === id)! as { source: string; maxzoom?: number; paint: Record<string, unknown> };
    expect(get("fill-hex4").maxzoom).toBe(5);
    expect(get("fill-hex5").maxzoom).toBeUndefined();
    expect(get("fill-hex6").maxzoom).toBeUndefined();
    expect(get("fill-hex5").source).toBe("hexes");
    expect(get("fill-hex6").source).toBe("hexes_fine");
    expect(get("fill-hex5").paint["fill-opacity"]).toEqual(["step", ["zoom"], 0.85, 8, ["case", ["==", ["get", "ref"], true], 0, 0.85]]);
    expect(get("fill-hex6").paint["fill-opacity"]).toEqual(["step", ["zoom"], 0.85, 10, ["case", ["==", ["get", "ref"], true], 0, 0.85]]);
    expect(get("fill-hex4").paint["fill-opacity"]).toBe(0.85); // hex4 stops before a finer layer starts drawing over it
    expect(get("fill-hex7").paint["fill-opacity"]).toBe(0.85);
    expect(get("selected-hex5").paint["line-opacity"]).toEqual(["step", ["zoom"], 1, 8, ["case", ["==", ["get", "ref"], true], 0, 1]]);
    expect(validateStyleMin(styleWith(layers) as never).map((e) => e.message)).toEqual([]);
  });

  it("hides the hatch when confidence is off and the national outline outside wellbeing views", () => {
    const layers = buildLayers({ view: "heat", dims: DIMS, weights: {}, picks: PICKS }, true, false, LAYERS);
    const hatch = layers.find((l) => l.id === "hatch-hex4")!;
    const national = layers.find((l) => l.id === "national-hex4")!;
    expect((hatch as { layout?: { visibility?: string } }).layout?.visibility).toBe("none");
    expect((national as { layout?: { visibility?: string } }).layout?.visibility).toBe("none");
  });

  it("builds a seamless hatch image", () => {
    const img = hatchImage(16);
    expect(img.width).toBe(16);
    expect(img.data.length).toBe(16 * 16 * 4);
    const painted = Array.from({ length: 256 }, (_, i) => img.data[i * 4 + 3] > 0).filter(Boolean).length;
    expect(painted).toBe(64); // 2 of every 8 pixels along the diagonal period
  });
});

describe("theme change keeps the hex stack (setStyle transformStyle)", () => {
  const hexLayers = buildLayers({ view: "bivar", dims: DIMS, weights: {}, picks: PICKS, theme: "dark" }, false, true, [LAYERS[0]]);
  const prev: StyleSpecification = {
    version: 8,
    sources: { basemap: { type: "vector", tiles: ["https://old/{z}/{x}/{y}.pbf"] }, [SOURCE_ID]: { type: "vector", url: "pmtiles://x" } },
    layers: [{ id: "land", type: "fill", source: "basemap", "source-layer": "land" }, ...hexLayers, { id: "place-labels", type: "symbol", source: "basemap", "source-layer": "place" }],
  };
  const next: StyleSpecification = {
    version: 8,
    sources: { basemap: { type: "vector", tiles: ["https://new/{z}/{x}/{y}.pbf"] } },
    layers: [
      { id: "water", type: "fill", source: "basemap", "source-layer": "water" },
      { id: "roads", type: "line", source: "basemap", "source-layer": "roads" },
      { id: "labels", type: "symbol", source: "basemap", "source-layer": "place" },
    ],
  };

  it("carries the hex source and layers over, under the first symbol layer", () => {
    const merged = mergeStyleOnThemeChange(prev, next);
    expect(Object.keys(merged.sources)).toEqual(["basemap", SOURCE_ID]);
    expect(merged.layers.map((l) => l.id)).toEqual(["water", "roads", ...KINDS.map((k) => `${k}-hex4`), "labels"]);
    expect(validateStyleMin(merged as never).map((e) => e.message)).toEqual([]);
    expect(isHexLayerId("fill-hex4")).toBe(true);
    expect(isHexLayerId("water")).toBe(false);
  });

  it("carries every hex source when layers come from two archives", () => {
    const vector = { type: "vector" as const, tiles: ["https://example.org/{z}/{x}/{y}.pbf"] };
    const layers = buildLayers({ view: "bivar", dims: DIMS, weights: {}, picks: PICKS }, false, true, tileLayersFrom(TILES));
    const two: StyleSpecification = { version: 8, sources: { [SOURCE_ID]: vector, hexes_fine: vector }, layers };
    const merged = mergeStyleOnThemeChange(two, next);
    expect(Object.keys(merged.sources).sort()).toEqual(["basemap", "hexes", "hexes_fine"]);
    expect(validateStyleMin(merged as never).map((e) => e.message)).toEqual([]);
  });

  it("returns the next style untouched when there is nothing to carry", () => {
    expect(mergeStyleOnThemeChange(undefined, next)).toBe(next);
    expect(mergeStyleOnThemeChange({ version: 8, sources: {}, layers: [] }, next)).toBe(next);
  });
});
