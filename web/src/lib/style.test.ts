import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { hatchImage } from "./hatch";
import { buildLayers, fillLayerIds, isHexLayerId, layerId, mergeStyleOnThemeChange, SOURCE_ID } from "./style";

const dim = (id: string, group: DimInfo["group"], higher_is: DimInfo["higher_is"] = "better"): DimInfo => ({ id, name: id, group, kind: "score", higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "hazard", "worse"), dim("wb", "wellbeing"), dim("jobs", "life")];
const LAYERS = [
  { name: "hex4", minzoom: 2, maxzoom: 4 },
  { name: "hex5", minzoom: 5, maxzoom: 7 },
];
const PICKS = { pol: "competitive", race: "diverse" } as const;
const KINDS = ["fill", "hatch", "national", "hover", "halo", "selected"];

function styleWith(layers: ReturnType<typeof buildLayers>): StyleSpecification {
  return { version: 8 as const, sources: { [SOURCE_ID]: { type: "vector" as const, tiles: ["https://example.org/{z}/{x}/{y}.pbf"] } }, layers };
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

  it("returns the next style untouched when there is nothing to carry", () => {
    expect(mergeStyleOnThemeChange(undefined, next)).toBe(next);
    expect(mergeStyleOnThemeChange({ version: 8, sources: {}, layers: [] }, next)).toBe(next);
  });
});
