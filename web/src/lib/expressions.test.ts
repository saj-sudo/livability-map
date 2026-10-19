import { createExpression, latest } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { bivarColor, compositeExpression, hatchFilter, inhabitedFilter, matchExpr, priorityColor, scoreColor } from "./expressions";
import { GREY, PALETTES, RAMP_HAZARD } from "./palette";

const dim = (id: string, kind: DimInfo["kind"] = "score", higher_is: DimInfo["higher_is"] = "better", group: DimInfo["group"] = "life"): DimInfo => ({ id, name: id, group, kind, higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "score", "worse", "hazard"), dim("jobs"), dim("pol", "signed"), dim("race", "composition")];

// colour expressions are compiled against the fill-color spec so string stops coerce to colours,
// exactly as MapLibre does for a paint property
const FILL_COLOR = (latest as unknown as { paint_fill: Record<string, unknown> }).paint_fill["fill-color"];

function evaluate(expr: unknown, properties: Record<string, unknown>, spec?: unknown): unknown {
  const compiled = createExpression(expr as never, spec as never);
  if (compiled.result !== "success") throw new Error(JSON.stringify(compiled.value));
  return compiled.value.evaluate({ zoom: 5 } as never, { type: "Polygon", properties, geometry: [] } as never);
}

describe("composite (SPEC §20.5)", () => {
  it("weights present dimensions and flips higher_is worse", () => {
    const e = compositeExpression(DIMS, { heat: 1, jobs: 3 }, { pol: "competitive" });
    // heat score 80 -> match 20; jobs score 60 -> 60; (1*20 + 3*60) / 4 = 50
    expect(evaluate(e, { heat_score: 80, jobs_score: 60 })).toBe(50);
  });

  it("drops missing dimensions from the denominator (invariant 3)", () => {
    const e = compositeExpression(DIMS, { heat: 1, jobs: 3 }, { pol: "competitive" });
    expect(evaluate(e, { heat_score: 80 })).toBe(20);
    expect(evaluate(e, {})).toBe(-1);
  });

  it("handles the signed pick", () => {
    const left = compositeExpression(DIMS, { pol: 1 }, { pol: "left" });
    expect(evaluate(left, { pol_lean: 60 })).toBe(80);
    const right = compositeExpression(DIMS, { pol: 1 }, { pol: "right" });
    expect(evaluate(right, { pol_lean: 60 })).toBe(20);
    const comp = compositeExpression(DIMS, { pol: 1 }, { pol: "competitive" });
    expect(evaluate(comp, { pol_lean: -60 })).toBe(40);
  });

  it("never weights a composition dimension, even when a weight arrives (SPEC §13.39)", () => {
    const shares = { race_w: 20, race_b: 70, race_h: 5, race_a: 3, race_o: 2 };
    expect(compositeExpression(DIMS, { race: 3 }, { pol: "competitive" })).toBe(-1);
    expect(evaluate(compositeExpression(DIMS, { race: 3, jobs: 1 }, { pol: "competitive" }), { ...shares, jobs_score: 40 })).toBe(40);
    expect(() => matchExpr(DIMS.find((d) => d.id === "race")!, { pol: "competitive" })).toThrow(/context only/);
  });

  it("colours grey when nothing weighted is present", () => {
    const c = priorityColor(DIMS, { jobs: 2 }, { pol: "competitive" });
    expect(evaluate(c, {}, FILL_COLOR)).toEqual(evaluate(["to-color", GREY], {}, FILL_COLOR));
    expect(evaluate(c, { jobs_score: 100 }, FILL_COLOR)).not.toEqual(evaluate(["to-color", GREY], {}, FILL_COLOR));
  });
});

describe("layer expressions (SPEC §9.3)", () => {
  it("bivariate colours classes and greys class 0", () => {
    const grey = evaluate(["to-color", GREY], {}, FILL_COLOR);
    expect(evaluate(bivarColor(), { bivar: 0 }, FILL_COLOR)).toEqual(grey);
    expect(evaluate(bivarColor(), {}, FILL_COLOR)).toEqual(grey);
    expect(evaluate(bivarColor(), { bivar: 9 }, FILL_COLOR)).toEqual(evaluate(["to-color", PALETTES.light.bivar[9]], {}, FILL_COLOR));
  });

  it("score ramp greys missing data and reads flags", () => {
    const c = scoreColor("heat", RAMP_HAZARD);
    const grey = evaluate(["to-color", GREY], {}, FILL_COLOR);
    expect(evaluate(c, {}, FILL_COLOR)).toEqual(grey);
    expect(evaluate(c, { heat_score: 50, heat_ok: false }, FILL_COLOR)).toEqual(grey);
    expect(evaluate(c, { heat_score: 100, heat_ok: true }, FILL_COLOR)).toEqual(evaluate(["to-color", RAMP_HAZARD[2]], {}, FILL_COLOR));
  });

  it("filters", () => {
    expect(evaluate(inhabitedFilter(false), { inhabited: true })).toBe(true);
    expect(evaluate(inhabitedFilter(false), { inhabited: false })).toBe(false);
    expect(evaluate(inhabitedFilter(true), { inhabited: false })).toBe(true);
    expect(evaluate(hatchFilter(), { coverage: 3 })).toBe(true);
    expect(evaluate(hatchFilter(), { coverage: 4 })).toBe(false);
  });
});
