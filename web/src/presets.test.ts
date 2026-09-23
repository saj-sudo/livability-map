import { describe, expect, it } from "vitest";
import { DIM_ORDER, HAZARD_IDS } from "./lib/dims";
import { PRESETS, presetById } from "./presets";

describe("presets (SPEC §20.5)", () => {
  it("reference known dimensions with weights in 1..5", () => {
    for (const p of PRESETS) {
      const ids = Object.keys(p.weights);
      expect(ids.length).toBeGreaterThan(0);
      for (const id of ids) {
        expect(DIM_ORDER as readonly string[]).toContain(id);
        expect(p.weights[id]).toBeGreaterThan(0);
        expect(p.weights[id]).toBeLessThanOrEqual(5);
      }
    }
  });

  it("climate first uses the four hazards only", () => {
    const climate = PRESETS.find((p) => p.id === "climate")!;
    expect(Object.keys(climate.weights).sort()).toEqual([...HAZARD_IDS].sort());
  });

  it("early career weights cost of living and rent; retiring weights cost of living", () => {
    const early = PRESETS.find((p) => p.id === "early")!;
    expect(early.weights.cost).toBe(2);
    expect(early.weights.rent).toBe(2);
    const retiring = PRESETS.find((p) => p.id === "retiring")!;
    expect(retiring.weights.cost).toBe(2);
    expect(retiring.weights.rent).toBeUndefined();
  });

  it("use the NGO layers where they fit the persona", () => {
    const w = (id: string) => presetById(id)!.weights;
    expect(w("early").city).toBeGreaterThan(0);
    expect(w("kids").conflict).toBeGreaterThan(0);
    expect(w("kids").water).toBeGreaterThan(0);
    expect(w("retiring").walkcare).toBeGreaterThan(0);
  });
});
