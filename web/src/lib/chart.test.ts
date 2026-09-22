import { createExpression } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";
import { compositeValue, matchValue, missingCount, priorityBars } from "./chart";
import type { DimInfo } from "./dims";
import { compositeExpression, type Picks } from "./expressions";

const dim = (id: string, kind: DimInfo["kind"] = "score", higher_is: DimInfo["higher_is"] = "better", group: DimInfo["group"] = "life"): DimInfo => ({ id, name: id, group, kind, higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "score", "worse", "hazard"), dim("jobs"), dim("house", "score", "worse"), dim("pol", "signed"), dim("race", "composition")];

function evalExpr(expr: unknown, properties: Record<string, unknown>): unknown {
  const compiled = createExpression(expr as never);
  if (compiled.result !== "success") throw new Error(JSON.stringify(compiled.value));
  return compiled.value.evaluate({ zoom: 5 } as never, { type: "Polygon", properties, geometry: [] } as never);
}

const CASES: { name: string; weights: Record<string, number>; picks: Picks; props: Record<string, unknown> }[] = [
  { name: "scores with a worse-is-better flip", weights: { heat: 1, jobs: 3 }, picks: { pol: "competitive", race: "diverse" }, props: { heat_score: 80, jobs_score: 60 } },
  { name: "a missing dimension leaves the denominator", weights: { heat: 1, jobs: 3, house: 2 }, picks: { pol: "competitive", race: "diverse" }, props: { heat_score: 80 } },
  { name: "signed left", weights: { pol: 2, jobs: 1 }, picks: { pol: "left", race: "diverse" }, props: { pol_lean: 60, jobs_score: 10 } },
  { name: "signed right", weights: { pol: 1 }, picks: { pol: "right", race: "diverse" }, props: { pol_lean: 60 } },
  { name: "signed competitive", weights: { pol: 1 }, picks: { pol: "competitive", race: "diverse" }, props: { pol_lean: -60 } },
  { name: "composition diverse", weights: { race: 1 }, picks: { pol: "competitive", race: "diverse" }, props: { race_w: 20, race_b: 20, race_h: 20, race_a: 20, race_o: 20 } },
  { name: "composition specific group", weights: { race: 1, heat: 1 }, picks: { pol: "competitive", race: "b" }, props: { race_w: 20, race_b: 70, race_h: 5, race_a: 3, race_o: 2, heat_score: 10 } },
];

describe("chart model agrees with the map expression (SPEC §20.5)", () => {
  for (const c of CASES) {
    it(c.name, () => {
      const fromMap = evalExpr(compositeExpression(DIMS, c.weights, c.picks), c.props) as number;
      const fromTs = compositeValue(DIMS, c.weights, c.picks, c.props);
      expect(fromTs).not.toBeNull();
      expect(fromTs!).toBeCloseTo(fromMap, 6);
    });
  }

  it("is null (never 0) when no weighted dimension has data, matching the -1 sentinel", () => {
    expect(evalExpr(compositeExpression(DIMS, { jobs: 2 }, { pol: "competitive", race: "diverse" }), {})).toBe(-1);
    expect(compositeValue(DIMS, { jobs: 2 }, { pol: "competitive", race: "diverse" }, {})).toBeNull();
    expect(compositeValue(DIMS, {}, { pol: "competitive", race: "diverse" }, { jobs_score: 50 })).toBeNull();
    expect(matchValue(dim("jobs"), { jobs_score: null }, { pol: "competitive", race: "diverse" })).toBeNull();
  });

  it("lists weighted dimensions heaviest first with null for missing", () => {
    const bars = priorityBars({ heat_score: 80, jobs_score: 60 }, DIMS, { heat: 1, jobs: 3, house: 2 }, { pol: "competitive", race: "diverse" });
    expect(bars.map((b) => [b.id, b.weight, b.match])).toEqual([
      ["jobs", 3, 60],
      ["house", 2, null],
      ["heat", 1, 20],
    ]);
    expect(missingCount(bars)).toEqual({ missing: 1, total: 3 });
  });
});
