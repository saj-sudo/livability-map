import { describe, expect, it } from "vitest";
import { priorityBars } from "./chart";
import type { ClientManifest } from "./clientManifest";
import type { DimInfo } from "./dims";
import { describeHex } from "./inspect";
import { exposureLevel, leadLines, MISSING_NAMED } from "./lead";

const dim = (id: string, name: string, group: DimInfo["group"], higher_is: DimInfo["higher_is"] = "better", scale: DimInfo["scale"] = "percentile"): DimInfo => ({ id, name, group, kind: "score", higher_is, chip: "", note: "", scale, available: true, units: {} });
const DIMS: DimInfo[] = [
  dim("heat", "Extreme heat (days > 35C)", "hazard", "worse"),
  dim("humid", "Humid heat", "hazard", "worse"),
  dim("rflood", "Riverine flood", "hazard", "worse"),
  dim("cflood", "Coastal flood", "hazard", "worse"),
  dim("wstress", "Water stress", "hazard", "worse"),
  dim("wb", "Wellbeing", "wellbeing", "better", "minmax"),
  dim("air", "Air quality (fine particulate matter)", "env", "worse"),
  dim("trees", "Tree cover", "env"),
  dim("jobs", "Early-career job market", "life"),
  dim("house", "Housing cost burden", "life", "worse"),
  dim("transit", "Public transit access", "life"),
  dim("school", "Schools", "life"),
];
const MANIFEST: ClientManifest = { built_at: null, scenario: "rcp45_ssp245", horizon: "2050", non_commercial: true, tiles: {}, sources: [], dimensionSources: {}, notes: {} };
const PICKS = { pol: "competitive" } as const;

// a fixture-like hexagon: all five hazards, national wellbeing, dirty air, no transit or schools
const PLACE = {
  iso_a2: "XB", admin1_name: "B-Mid", population: 871095, inhabited: true,
  heat_days: 30, heat_score: 48, heat_ok: true, humid_days: 13, humid_score: 67, humid_ok: true,
  rflood_frac: 0.215, rflood_score: 89, rflood_ok: true, cflood_frac: 0, cflood_score: 48, cflood_ok: true, wstress_cat: 3, wstress_score: 73, wstress_ok: true,
  coverage: 5, exposure: 65, wb_value: 5.1, wb_score: 50, wb_source: "whr", wb_res: "national", bivar: 6,
  air_res: "hex", air_raw: 34.7, air_score: 99, trees_res: "hex", trees_raw: 12, trees_score: 35,
  jobs_res: "grid", jobs_raw: 0.82, jobs_score: 98, house_res: "area", house_raw: 20, house_score: 2, transit_res: "none", school_res: "none",
};
const lines = (props: Record<string, unknown>, weights: Record<string, number> = {}, preset: string | null = null) => {
  const m = describeHex(props, "hex4", DIMS, MANIFEST);
  return leadLines(m, priorityBars(props, DIMS, weights, PICKS), DIMS, weights, PICKS, props, preset);
};
const line = (ls: ReturnType<typeof lines>, key: string) => ls.find((l) => l.key === key);

describe("place panel lead lines (SPEC §10, §13.50)", () => {
  it("is at most five lines, in the rule's order, with no fit line until something is weighted", () => {
    const ls = lines(PLACE);
    expect(ls.map((l) => l.key)).toEqual(["climate", "wellbeing", "today", "missing"]);
    expect(lines(PLACE, { jobs: 3, house: 2, transit: 2 }).map((l) => l.key)).toEqual(["climate", "fit", "wellbeing", "today", "missing"]);
    expect(lines(PLACE, { jobs: 3 }).length).toBeLessThanOrEqual(5);
  });

  it("states combined exposure as what it is (an average of ranks) and names the hazard that ranks highest with its raw value", () => {
    const c = line(lines(PLACE), "climate")!;
    expect(c.label).toBe("Climate in 2050");
    expect(c.text).toMatch(/^Fairly high: 65 of 100, the average of the hazard ranks here\./);
    expect(c.text).toMatch(/Riverine flood ranks highest \(.*higher than 89% of inhabited places\)/);
    expect(c.text).not.toMatch(/more exposed than/); // the combined number is not itself a rank
    expect(c.text).not.toMatch(/less certain/);
    const partial = line(lines({ ...PLACE, cflood_ok: false, coverage: 4 }), "climate")!;
    expect(partial.text).toMatch(/Only 4 of 5 hazard layers have data/);
  });

  it("uses the map's five exposure steps for its words", () => {
    expect([0, 19, 20, 45, 65, 80, 100].map(exposureLevel)).toEqual(["Low", "Low", "Fairly low", "Middling", "Fairly high", "High", "High"]);
  });

  it("says plainly when wellbeing is only a national figure", () => {
    expect(line(lines(PLACE), "wellbeing")!.text).toMatch(/^Only a national figure exists here \(life evaluation 5\.10 \/ 10\)\. It says nothing about this area in particular\.$/);
    expect(line(lines({ ...PLACE, wb_res: "admin1", wb_source: "shdi", wb_value: 0.82 }), "wellbeing")!.text).toBe("Subnational HDI 0.820, a regional figure.");
  });

  it("picks the present-day measure furthest from the middle, with its direction in words, never an unranked one", () => {
    const t = line(lines(PLACE), "today")!;
    expect(t.text).toMatch(/^Air quality: .*higher than 99% of inhabited places\. More of it is worse\.$/);
    // nothing far enough from the middle: no line, not a filler
    const dull = { ...PLACE, air_score: 55, trees_score: 45, jobs_score: 60, house_score: 40 };
    expect(line(lines(dull), "today")).toBeUndefined();
  });

  it("names the priorities fit as a band, with what pulls it up, down, and what was left out", () => {
    const f = line(lines(PLACE, { jobs: 3, house: 2, transit: 2 }, "Early career"), "fit")!;
    expect(f.label).toBe("Fit with Early career");
    // jobs 98 (w3) + housing burden 100 - 2 = 98 (w2) -> 98: strong
    expect(f.text).toMatch(/^A strong fit\./);
    expect(f.text).toMatch(/Pulled up by early-career job market and housing cost burden\./);
    expect(f.text).toMatch(/Left out for lack of data: public transit access\./);
    expect(f.text).not.toMatch(/\d+\/100|\d+ of 100/); // the figure is one step in, not in the lead
    expect(line(lines(PLACE, { transit: 2 }), "fit")!.text).toMatch(/^None of the measures you weighted has data here/);
  });

  it("names what is not measured and never calls it zero", () => {
    const miss = line(lines(PLACE), "missing")!;
    expect(miss.text).toBe("Public transit access and schools. No data, which is not the same as zero.");
    const many = line(lines({ ...PLACE, air_res: "none", trees_res: "none", jobs_res: "none", house_res: "none" }), "missing")!;
    expect(many.text).toMatch(new RegExp(`, and ${6 - MISSING_NAMED} more\\.`));
    const noHaz = lines({ ...PLACE, heat_ok: false, humid_ok: false, rflood_ok: false, cflood_ok: false, wstress_ok: false, coverage: 0, exposure: undefined });
    expect(noHaz[0].text).toMatch(/missing data, not zero risk/);
    expect(line(noHaz, "climate")).toBeUndefined();
  });

  it("keeps the uninhabited sentence and scores nothing but the hazards there", () => {
    const ls = lines({ ...PLACE, inhabited: false, population: 0 }, { jobs: 3 });
    expect(ls[0].text).toMatch(/Fewer than 100 people live here/);
    expect(ls.map((l) => l.key)).toEqual(["note", "climate"]);
  });
});
