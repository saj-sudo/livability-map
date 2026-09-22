import { describe, expect, it } from "vitest";
import { DIM_ORDER, dimensionsFrom, lifeDims } from "./dims";
import { EMPTY_MANIFEST } from "./manifest";

describe("dimension registry (SPEC §20.2)", () => {
  it("appends new dimensions to DIM_ORDER so old `w=` links keep their meaning", () => {
    // the first fourteen slots are frozen: hazards, wellbeing, then the Session 4 life dimensions
    expect(DIM_ORDER.slice(0, 14)).toEqual(["heat", "rflood", "cflood", "wstress", "wb", "jobs", "transit", "school", "lgbtq", "pol", "race", "incmix", "house", "health"]);
    expect(DIM_ORDER.slice(14)).toEqual(["cost", "rent"]);
    expect(new Set(DIM_ORDER).size).toBe(DIM_ORDER.length);
  });

  it("falls back to a registry that mirrors dimensions.yaml when the manifest is empty", () => {
    const dims = dimensionsFrom(EMPTY_MANIFEST);
    expect(dims.map((d) => d.id)).toEqual([...DIM_ORDER]);
    const cost = lifeDims(dims).find((d) => d.id === "cost")!;
    expect(cost.kind).toBe("score");
    expect(cost.higher_is).toBe("worse"); // a higher price level is worse for the person
    expect(cost.chip).toBe("Global / US");
    const rent = lifeDims(dims).find((d) => d.id === "rent")!;
    expect(rent.higher_is).toBe("worse");
    expect(rent.chip).toBe("US only");
  });
});
