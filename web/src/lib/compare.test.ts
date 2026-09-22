import { describe, expect, it } from "vitest";
import type { ClientManifest } from "./clientManifest";
import { compareRows } from "./compare";
import type { DimInfo } from "./dims";
import { describeHex } from "./inspect";

const dim = (id: string, kind: DimInfo["kind"], group: DimInfo["group"], higher_is: DimInfo["higher_is"] = "better"): DimInfo => ({ id, name: id, group, kind, higher_is, chip: "", note: "", scale: "percentile", available: true });
const DIMS: DimInfo[] = [dim("heat", "score", "hazard", "worse"), dim("rflood", "score", "hazard", "worse"), dim("cflood", "score", "hazard", "worse"), dim("wstress", "score", "hazard", "worse"), dim("wb", "score", "wellbeing"), dim("jobs", "score", "life"), dim("house", "score", "life", "worse"), dim("pol", "signed", "life")];
const MANIFEST: ClientManifest = { built_at: null, scenario: "rcp45_ssp245", horizon: "2050", non_commercial: true, tiles: {}, sources: [], dimensionSources: {}, notes: {} };
const PICKS = { pol: "competitive", race: "diverse" } as const;

const A = { iso_a2: "US", admin1_name: "Colorado", population: 2000, inhabited: true, heat_days: 37, heat_score: 66, heat_ok: true, rflood_ok: false, cflood_ok: false, wstress_ok: false, coverage: 1, exposure: 66, wb_value: 6.8, wb_score: 85, wb_source: "whr", wb_res: "national", bivar: 9, jobs_res: "tract", jobs_raw: 0.95, jobs_score: 73, house_res: "tract", house_raw: 32, house_score: 81, pol_res: "county", pol_lean: 10 };
const B = { iso_a2: "BD", admin1_name: "Dhaka", population: 13000000, inhabited: true, heat_days: 90, heat_score: 90, heat_ok: true, rflood_ok: false, cflood_ok: false, wstress_ok: false, coverage: 1, exposure: 90, wb_value: 4.1, wb_score: 35, wb_source: "whr", wb_res: "national", bivar: 3, jobs_res: "national", jobs_raw: 84, jobs_score: 40, house_res: "none", pol_res: "none" };

const side = (p: Record<string, unknown>) => ({ model: describeHex(p, "hex4", DIMS, MANIFEST), props: p });

describe("compare two places (SPEC §10)", () => {
  const rows = compareRows(side(A), side(B), DIMS, { heat: 1, jobs: 2 }, PICKS);
  const row = (id: string) => rows.find((r) => r.id === id)!;

  it("leans towards less hazard, more wellbeing and the dimension's own direction", () => {
    expect(row("heat").leans).toBe("a"); // 66 < 90: less heat is better
    expect(row("wb").leans).toBe("a");
    expect(row("jobs").leans).toBe("a"); // 73 > 40
    expect(row("match").a).toBe("60/100"); // heat match 34 (w1) + jobs 73 (w2) -> (34 + 146) / 3
    expect(row("match").leans).toBe("a");
  });

  it("never lets a missing side win and never shows it as zero", () => {
    expect(row("house").a).toBe("32% of income on rent, 81/100");
    expect(row("house").b).toBeNull();
    expect(row("house").leans).toBeNull();
    expect(row("rflood").a).toBeNull();
    expect(row("rflood").leans).toBeNull();
  });

  it("carries the combined class in words and skips leaning on it", () => {
    expect(row("bivar").a).toBe("high exposure, high wellbeing");
    expect(row("bivar").b).toBe("high exposure, low wellbeing");
    expect(row("bivar").leans).toBeNull();
    expect(row("pol").a).toBe("D+10 (two-party margin)");
    expect(row("pol").leans).toBeNull(); // signed: no "better"
  });

  it("omits the priorities row when nothing is weighted", () => {
    expect(compareRows(side(A), side(B), DIMS, {}, PICKS).some((r) => r.id === "match")).toBe(false);
  });
});
