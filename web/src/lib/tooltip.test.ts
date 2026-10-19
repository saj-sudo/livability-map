import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { tooltipModel } from "./tooltip";

const dim = (id: string, name: string, group: DimInfo["group"] = "life", higher_is: DimInfo["higher_is"] = "better"): DimInfo => ({ id, name, group, kind: "score", higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "Extreme heat (days > 35C)", "hazard", "worse"), dim("wb", "Wellbeing", "wellbeing"), dim("jobs", "Early-career job market")];
const PICKS = { pol: "competitive" } as const;
const FULL = { iso_a2: "BD", admin1_name: "Dhaka", population: 13906075, bivar: 6, heat_days: 33.6, heat_score: 66, heat_ok: true, jobs_res: "national", jobs_raw: 84, jobs_score: 40, wb_res: "none" };

describe("hover readout (SPEC §10)", () => {
  it("names the place and reads the bivariate class in words", () => {
    const t = tooltipModel(FULL, "bivar", DIMS, {}, PICKS);
    expect(t.title).toBe("Dhaka");
    expect(t.subtitle).toBe("Bangladesh, 13,906,075 people");
    expect(t.line).toBe("high exposure, medium wellbeing");
    expect(t.bivar).toBe(6);
    expect(t.slim).toBe(false);
  });

  it("says to zoom in on slim tiles and never invents a value", () => {
    const t = tooltipModel({ bivar: 3 }, "bivar", DIMS, {}, PICKS);
    expect(t.slim).toBe(true);
    expect(t.title).toMatch(/zoom in/i);
    expect(tooltipModel({}, "bivar", DIMS, {}, PICKS).line).toBe("no data");
    expect(tooltipModel({}, "bivar", DIMS, {}, PICKS).bivar).toBe(0);
  });

  it("reads a single layer with its raw value, and 'no data' when the flag is off", () => {
    expect(tooltipModel(FULL, "heat", DIMS, {}, PICKS).line).toBe("Extreme heat: 66/100, 34 days/yr");
    expect(tooltipModel({ ...FULL, heat_ok: false }, "heat", DIMS, {}, PICKS).line).toBe("Extreme heat: no data");
    expect(tooltipModel(FULL, "wb", DIMS, {}, PICKS).line).toBe("Wellbeing: no data");
  });

  it("reads the priorities match and counts what is missing", () => {
    expect(tooltipModel(FULL, "priorities", DIMS, {}, PICKS).line).toBe("no priorities set yet");
    // heat 66 -> match 34 (w1); jobs 40 (w1); wb missing -> (34 + 40) / 2 = 37
    expect(tooltipModel(FULL, "priorities", DIMS, { heat: 1, jobs: 1, wb: 1 }, PICKS).line).toBe("matches your priorities 37/100 (1 of 3 missing here)");
    expect(tooltipModel({ iso_a2: "BD" }, "priorities", DIMS, { jobs: 2 }, PICKS).line).toBe("no data for any of your priorities");
  });
});
