import { describe, expect, it } from "vitest";
import { DIM_ORDER, HAZARD_IDS } from "./lib/dims";
import { PRESETS } from "./presets";

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
});
