import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { areaLine, formatDimRaw, formatHazardRaw, formatNumber, formatPopulation, formatScore, formatWithUnit, roughPopulation, unitFor } from "./format";

const dim = (id: string, units: DimInfo["units"] = {}): DimInfo => ({ id, name: id, group: "life", kind: "score", higher_is: "better", chip: "", note: "", scale: "percentile", available: true, units });

describe("formatting values (never 0 for missing)", () => {
  it("formats hazards with their units, null for missing", () => {
    expect(formatHazardRaw("heat", 33.6)).toBe("34 days/yr");
    expect(formatHazardRaw("rflood", 0.0234)).toBe("2.3% of area");
    expect(formatHazardRaw("cflood", 0)).toBe("0.0% of area");
    expect(formatHazardRaw("wstress", 3)).toBe("high");
    expect(formatHazardRaw("wstress", -1)).toContain("arid");
    expect(formatHazardRaw("heat", null)).toBeNull();
    expect(formatHazardRaw("other", 1234.5)).toBe("1,234.5");
  });

  it("picks the unit for the hex's tag, then the default, then any", () => {
    const d = dim("x", { "*": { unit: "dB", multiply: 1, decimals: 0 }, tract: { unit: "%", multiply: 100, decimals: 1 } });
    expect(unitFor(d, "tract")!.unit).toBe("%");
    expect(unitFor(d, "hex")!.unit).toBe("dB");
    expect(unitFor(dim("y", { county: { unit: "u", multiply: 1, decimals: 0 } }), "hex")!.unit).toBe("u");
    expect(unitFor(dim("z"), "hex")).toBeNull();
    expect(formatWithUnit(d, 0.1234, "tract")).toBe("12.3%");
    expect(formatWithUnit(d, 47.6, "hex")).toBe("48 dB");
    expect(formatWithUnit(dim("z"), 1, "hex")).toBeNull();
  });

  it("formats the life dimensions by source", () => {
    expect(formatDimRaw(dim("jobs"), 7.25, "admin1")).toBe("7.3 / 10 (OECD jobs score)");
    expect(formatDimRaw(dim("jobs"), 41, "national")).toBe("41% of 15-24s employed");
    expect(formatDimRaw(dim("house"), 31, "tract")).toBe("31% of income on rent");
    expect(formatDimRaw(dim("rent"), 1450.4, "county")).toBe("$1,450/month (2-bedroom FMR)");
    expect(formatDimRaw(dim("drought"), 2, "basin")).toBe("drought risk 2 of 4 (medium)");
    expect(formatDimRaw(dim("noise"), 3.5, "hex")).toBe("3.5");
    expect(formatDimRaw(dim("jobs"), null, "tract")).toBeNull();
  });

  it("prints plain numbers, scores and populations", () => {
    expect(formatNumber(1200)).toBe("1,200");
    expect(formatNumber(3.14159)).toBe("3.14");
    expect(formatScore(66.6)).toBe("67/100");
    expect(formatPopulation(784368)).toBe("784,368 people");
    expect(formatPopulation(null)).toBe("population unknown");
  });

  it("rounds a population the way a person says it", () => {
    expect(roughPopulation(42)).toBe("fewer than 100");
    expect(roughPopulation(345)).toBe("350");
    expect(roughPopulation(1234)).toBe("1,230");
    expect(roughPopulation(784368)).toBe("784,000");
    expect(roughPopulation(13906075)).toBe("13.9 million");
    expect(roughPopulation(2000000)).toBe("2 million");
    expect(roughPopulation(123456789)).toBe("123 million");
  });

  it("builds the area line without jargon", () => {
    expect(areaLine(784368, "1,770")).toBe("About 784,000 people in this ~1,770 km² area");
    expect(areaLine(null, "253")).toBe("Population unknown in this ~253 km² area");
    expect(areaLine(0, "253")).toBe("No one lives in this ~253 km² area");
    expect(areaLine(40, null)).toBe("Fewer than 100 people in this area");
    expect(areaLine(784368, "1,770")).not.toMatch(/hex|res \d/);
  });
});
