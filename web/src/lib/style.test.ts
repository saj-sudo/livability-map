import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { StyleSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { hatchImage } from "./hatch";
import { TILES } from "./layers.test";
import { tileLayersFrom } from "./layers";
import { basemapStyle, COUNTRY_TOP_ID } from "./basemap";
import { buildLayers, fillLayerIds, hexAnchorIndex, isHexLayerId, layerId, mergeStyleOnThemeChange, pickVisible, showsCountryBorders, SOURCE_ID } from "./style";

const dim = (id: string, group: DimInfo["group"], higher_is: DimInfo["higher_is"] = "better"): DimInfo => ({ id, name: id, group, kind: "score", higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "hazard", "worse"), dim("wb", "wellbeing"), dim("jobs", "life")];
const LAYERS = tileLayersFrom({ hexes: { key: "hexes.pmtiles", sha256: "", bytes: 1, minzoom: 2, maxzoom: 7, layers: [{ name: "hex4", minzoom: 2, maxzoom: 4 }, { name: "hex5", minzoom: 5, maxzoom: 7 }] } });
const PICKS = { pol: "competitive" } as const;
const KINDS = ["fill", "hatch", "hover", "halo", "selected"];

function styleWith(layers: ReturnType<typeof buildLayers>): StyleSpecification {
  const vector = { type: "vector" as const, tiles: ["https://example.org/{z}/{x}/{y}.pbf"] };
  return { version: 8 as const, sources: { [SOURCE_ID]: vector, hexes_nbhd: vector, hexes_city: vector }, layers };
}

describe("layer stack (SPEC §9.3)", () => {
  it("is a valid MapLibre style for every view and both themes", () => {
    for (const theme of ["light", "dark"] as const) {
      for (const view of ["exp", "bivar", "heat", "wb", "priorities"] as const) {
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
    expect(get("fill-hex6").source).toBe("hexes_nbhd");
    expect(get("fill-hex5").paint["fill-opacity"]).toEqual(["step", ["zoom"], 0.85, 8, ["case", ["==", ["get", "ref"], true], 0, 0.85]]);
    expect(get("fill-hex6").paint["fill-opacity"]).toEqual(["step", ["zoom"], 0.85, 10, ["case", ["==", ["get", "ref"], true], 0, 0.85]]);
    expect(get("fill-hex4").paint["fill-opacity"]).toBe(0.85); // hex4 stops before a finer layer starts drawing over it
    expect(get("fill-hex7").paint["fill-opacity"]).toBe(0.85);
    expect(get("selected-hex5").paint["line-opacity"]).toEqual(["step", ["zoom"], 1, 8, ["case", ["==", ["get", "ref"], true], 0, 1]]);
    expect(validateStyleMin(styleWith(layers) as never).map((e) => e.message)).toEqual([]);
  });

  it("never picks a hidden refined parent on hover or click (final review I1)", () => {
    const L = tileLayersFrom(TILES);
    const parent = { sourceLayer: "hex5", properties: { h3: "p", ref: true } };
    const child = { sourceLayer: "hex6", properties: { h3: "c" } };
    const plain5 = { sourceLayer: "hex5", properties: { h3: "q" } };
    expect(pickVisible([parent, plain5], 9, L)).toBe(plain5); // parent hidden from z8: skip it
    expect(pickVisible([parent], 9, L)).toBeUndefined(); // nothing visible under the pointer
    expect(pickVisible([parent, child], 7, L)).toBe(parent); // below z8 the parent is still drawn
    expect(pickVisible([child], 9, L)).toBe(child);
  });

  it("hides the hatch when confidence is off, and has no per-hex national outline (§13.50)", () => {
    const layers = buildLayers({ view: "heat", dims: DIMS, weights: {}, picks: PICKS }, true, false, LAYERS);
    const hatch = layers.find((l) => l.id === "hatch-hex4")!;
    expect((hatch as { layout?: { visibility?: string } }).layout?.visibility).toBe("none");
    expect(layers.some((l) => l.id.startsWith("national-"))).toBe(false);
  });

  it("draws country borders above the hexes only in the bivariate view", () => {
    expect(showsCountryBorders("bivar")).toBe(true);
    for (const v of ["exp", "heat", "wb", "priorities"] as const) expect(showsCountryBorders(v)).toBe(false);
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

  it("carries the hex source and layers over, under the first symbol layer of a stock style", () => {
    const merged = mergeStyleOnThemeChange(prev, next);
    expect(Object.keys(merged.sources)).toEqual(["basemap", SOURCE_ID]);
    expect(merged.layers.map((l) => l.id)).toEqual(["water", "roads", ...KINDS.map((k) => `${k}-hex4`), "labels"]);
    expect(validateStyleMin(merged as never).map((e) => e.message)).toEqual([]);
    expect(isHexLayerId("fill-hex4")).toBe(true);
    expect(isHexLayerId("water")).toBe(false);
  });

  it("puts the hexes above every line of our own basemap and under its repeated country borders", () => {
    for (const theme of ["light", "dark"] as const) {
      const base = basemapStyle(theme);
      expect(validateStyleMin(base as never).map((e) => e.message)).toEqual([]);
      const merged = mergeStyleOnThemeChange(prev, base);
      const ids = merged.layers.map((l) => l.id);
      const firstHex = ids.indexOf("fill-hex4");
      const lastHex = ids.indexOf("selected-hex4");
      for (const below of ["background", "water", "region-line", "country-line"]) expect(ids.indexOf(below)).toBeLessThan(firstHex);
      expect(ids.indexOf(COUNTRY_TOP_ID)).toBe(lastHex + 1);
      for (const l of merged.layers.filter((x) => x.type === "symbol")) expect(ids.indexOf(l.id)).toBeGreaterThan(lastHex);
      // a quiet ground: no roads, no buildings
      expect(base.layers.some((l) => /road|transport|building/.test(JSON.stringify(l)))).toBe(false);
      expect(hexAnchorIndex(base.layers)).toBe(base.layers.findIndex((l) => l.id === COUNTRY_TOP_ID));
    }
    expect(hexAnchorIndex([{ id: "background", type: "background" }])).toBe(1); // the plain fallback: on top
  });

  it("carries every hex source when layers come from two archives", () => {
    const vector = { type: "vector" as const, tiles: ["https://example.org/{z}/{x}/{y}.pbf"] };
    const layers = buildLayers({ view: "bivar", dims: DIMS, weights: {}, picks: PICKS }, false, true, tileLayersFrom(TILES));
    const two: StyleSpecification = { version: 8, sources: { [SOURCE_ID]: vector, hexes_nbhd: vector, hexes_city: vector }, layers };
    const merged = mergeStyleOnThemeChange(two, next);
    expect(Object.keys(merged.sources).sort()).toEqual(["basemap", "hexes", "hexes_city", "hexes_nbhd"]);
    expect(validateStyleMin(merged as never).map((e) => e.message)).toEqual([]);
  });

  it("returns the next style untouched when there is nothing to carry", () => {
    expect(mergeStyleOnThemeChange(undefined, next)).toBe(next);
    expect(mergeStyleOnThemeChange({ version: 8, sources: {}, layers: [] }, next)).toBe(next);
  });
});
