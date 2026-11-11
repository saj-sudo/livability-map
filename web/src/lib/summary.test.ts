import { describe, expect, it } from "vitest";
import { priorityBars } from "./chart";
import type { DimInfo } from "./dims";
import type { HexModel } from "./inspect";
import { bivarPhrase, summarize } from "./summary";

const dim = (id: string, higher_is: DimInfo["higher_is"] = "better", group: DimInfo["group"] = "life"): DimInfo => ({ id, name: id, group, kind: "score", higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "worse", "hazard"), dim("jobs"), dim("house", "worse")];
const PICKS = { pol: "competitive" } as const;

const base: HexModel = {
  title: "Colorado",
  subtitle: "United States",
  population: "2,207,683 people",
  resolution: "H3 res 4 hex",
  inhabited: true,
  hazards: [],
  coverage: "4 of 4 hazard layers",
  exposure: 57,
  coverageN: 4,
  wellbeing: { value: "life evaluation 6.82 / 10", score: 85, source: "whr", res: "national" },
  bivar: "high exposure, high wellbeing",
  bivarClass: 9,
  env: [], life: [],
  sources: [],
};

describe("plain-language summary (SPEC §10)", () => {
  it("turns a bivariate class into a phrase", () => {
    expect(bivarPhrase(1)).toBe("low climate exposure and low wellbeing");
    expect(bivarPhrase(3)).toBe("high climate exposure and low wellbeing");
    expect(bivarPhrase(7)).toBe("low climate exposure and high wellbeing");
    expect(bivarPhrase(0)).toBeNull();
  });

  it("leads with the colour's meaning and flags the national wellbeing figure", () => {
    const s = summarize(base, [], DIMS, {}, PICKS, {});
    expect(s).toBe("Colorado shows high climate exposure and high wellbeing. All four hazard layers are present. Wellbeing is the national figure, not this region's.");
  });

  it("names reduced coverage and unclassified hexes without inventing values", () => {
    const partial = { ...base, coverageN: 2, bivarClass: 0, bivar: "not classified", wellbeing: { value: null, score: null, source: "none", res: "none" } };
    expect(summarize(partial, [], DIMS, {}, PICKS, {})).toBe("Colorado has hazard data but no wellbeing figure, so it is not classified. Only 2 of 4 hazard layers are present, so the exposure side is less certain.");
    const empty = { ...partial, coverageN: 0 };
    expect(summarize(empty, [], DIMS, {}, PICKS, {})).toContain("no hazard data");
    const desert = { ...base, inhabited: false };
    expect(summarize(desert, [], DIMS, {}, PICKS, {})).toMatch(/^Fewer than 100 people/);
  });

  it("adds the priorities match and what is missing", () => {
    const props = { heat_score: 80, jobs_score: 60 };
    const weights = { heat: 1, jobs: 3, house: 2 };
    const bars = priorityBars(props, DIMS, weights, PICKS);
    const s = summarize(base, bars, DIMS, weights, PICKS, props);
    expect(s).toContain("It matches your priorities 50/100, with 1 of 3 missing here.");
    expect(summarize(base, priorityBars({}, DIMS, weights, PICKS), DIMS, weights, PICKS, {})).toContain("None of your weighted dimensions has data here.");
  });
});
