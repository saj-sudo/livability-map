import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { hatchImage } from "./hatch";
import { buildLayers, fillLayerIds, layerId, SOURCE_ID } from "./style";

const dim = (id: string, group: DimInfo["group"], higher_is: DimInfo["higher_is"] = "better"): DimInfo => ({ id, name: id, group, kind: "score", higher_is, chip: "", note: "", scale: "percentile" });
const DIMS = [dim("heat", "hazard", "worse"), dim("wb", "wellbeing"), dim("jobs", "life")];
const LAYERS = [
  { name: "hex4", minzoom: 2, maxzoom: 4 },
  { name: "hex5", minzoom: 5, maxzoom: 7 },
];

function styleWith(layers: ReturnType<typeof buildLayers>) {
  return { version: 8 as const, sources: { [SOURCE_ID]: { type: "vector" as const, tiles: ["https://example.org/{z}/{x}/{y}.pbf"] } }, layers };
}

describe("layer stack (SPEC §9.3)", () => {
  it("is a valid MapLibre style for every view", () => {
    for (const view of ["bivar", "heat", "wb", "priorities"] as const) {
      const layers = buildLayers({ view, dims: DIMS, weights: { heat: 2, jobs: 1 }, picks: { pol: "competitive", race: "diverse" } }, false, true, LAYERS);
      const errors = validateStyleMin(styleWith(layers) as never);
      expect(errors.map((e) => e.message)).toEqual([]);
      expect(layers.map((l) => l.id)).toEqual(["fill-hex4", "hatch-hex4", "national-hex4", "selected-hex4", "fill-hex5", "hatch-hex5", "national-hex5", "selected-hex5"]);
    }
  });

  it("uses exclusive maxzoom below the top layer and overzooms the top layer", () => {
    const layers = buildLayers({ view: "bivar", dims: DIMS, weights: {}, picks: { pol: "competitive", race: "diverse" } }, false, true, LAYERS);
    const fill4 = layers.find((l) => l.id === layerId("fill", "hex4"))!;
    const fill5 = layers.find((l) => l.id === layerId("fill", "hex5"))!;
    expect(fill4.minzoom).toBe(2);
    expect(fill4.maxzoom).toBe(5);
    expect(fill5.minzoom).toBe(5);
    expect(fill5.maxzoom).toBeUndefined();
    expect(fillLayerIds(LAYERS)).toEqual(["fill-hex4", "fill-hex5"]);
  });

  it("hides the hatch when confidence is off and the national outline outside wellbeing views", () => {
    const layers = buildLayers({ view: "heat", dims: DIMS, weights: {}, picks: { pol: "competitive", race: "diverse" } }, true, false, LAYERS);
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
