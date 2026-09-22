import { describe, expect, it } from "vitest";
import type { ClientManifest } from "./clientManifest";
import type { DimInfo } from "./dims";
import { describeHex } from "./inspect";

const dim = (id: string, kind: DimInfo["kind"], group: DimInfo["group"], name = id): DimInfo => ({ id, name, group, kind, higher_is: "better", chip: group === "life" ? "US only" : "Global", note: "", scale: "percentile" });
const DIMS: DimInfo[] = [
  dim("heat", "score", "hazard", "Extreme heat"),
  dim("rflood", "score", "hazard"),
  dim("cflood", "score", "hazard"),
  dim("wstress", "score", "hazard"),
  dim("wb", "score", "wellbeing"),
  dim("jobs", "score", "life", "Jobs"),
  dim("pol", "signed", "life", "Political lean"),
  dim("race", "composition", "life", "Composition"),
  dim("cost", "score", "life", "Cost of living"),
  dim("rent", "score", "life", "Housing cost"),
  dim("care", "score", "life", "Travel time to healthcare"),
  dim("net", "score", "life", "Internet speed"),
  dim("air", "score", "env", "Air quality"),
  dim("trees", "score", "env", "Tree cover"),
  dim("fire", "score", "env", "Wildfire"),
  dim("drought", "score", "env", "Drought risk"),
];
const MANIFEST: ClientManifest = {
  built_at: "2026-09-22T00:00:00Z",
  scenario: "rcp45_ssp245",
  horizon: "2050",
  non_commercial: true,
  tiles: {},
  sources: [
    { id: "cckp_hd35", name: "CCKP", vintage: "2024", license: "CC BY 4.0", license_note: "", attribution: "WB", processing: "", url: null },
    { id: "whr_ladder", name: "WHR", vintage: "2026", license: "free", license_note: "", attribution: "WHR", processing: "", url: null },
    { id: "acs_summary", name: "ACS", vintage: "2024", license: "PD", license_note: "", attribution: "Census", processing: "", url: null },
    { id: "medsl_county_pres", name: "MEDSL", vintage: "2024", license: "CC0", license_note: "", attribution: "MIT", processing: "", url: null },
    { id: "ghsl_pop", name: "GHSL", vintage: "2023", license: "CC BY 4.0", license_note: "", attribution: "JRC", processing: "", url: null },
    { id: "acag_pm25", name: "ACAG PM2.5", vintage: "2024", license: "CC BY 4.0", license_note: "", attribution: "WashU", processing: "", url: null },
  ],
  dimensionSources: { heat: ["cckp_hd35"], jobs: ["acs_summary"], pol: ["medsl_county_pres"], race: ["acs_summary"], air: ["acag_pm25"] },
  notes: {},
};

describe("describeHex (SPEC §10 inspector)", () => {
  it("never shows a missing hazard or dimension as zero", () => {
    const props = { h3: "84x", iso_a2: "BD", admin1_name: "Dhaka", population: 13906075, inhabited: true, heat_days: 33.6, heat_score: 66, heat_ok: true, rflood_ok: false, cflood_ok: false, wstress_cat: -1, wstress_ok: false, coverage: 1, exposure: 66, wb_value: 4.1, wb_score: 35, wb_source: "whr", wb_res: "national", bivar: 6, jobs_res: "none", pol_res: "none", race_res: "none" };
    const m = describeHex(props, "hex4", DIMS, MANIFEST);
    expect(m.title).toBe("Dhaka");
    expect(m.subtitle).toBe("Bangladesh");
    expect(m.population).toBe("13,906,075 people");
    const heat = m.hazards.find((h) => h.id === "heat")!;
    expect(heat.raw).toBe("34 days/yr");
    expect(heat.score).toBe(66);
    const rflood = m.hazards.find((h) => h.id === "rflood")!;
    expect(rflood.raw).toBeNull();
    expect(rflood.score).toBeNull();
    expect(m.hazards.find((h) => h.id === "wstress")!.raw).toContain("arid");
    expect(m.coverage).toBe("1 of 4 hazard layers");
    expect(m.wellbeing).toEqual({ value: "life evaluation 4.10 / 10", score: 35, source: "whr", res: "national" });
    expect(m.bivar).toBe("high exposure, medium wellbeing");
    for (const row of m.life) {
      expect(row.res).toBe("none");
      expect(row.value).toBeNull();
      expect(row.score).toBeNull();
    }
    // sources: only what produced a shown value, plus the reference layers
    expect(m.sources.map((s) => s.id).sort()).toEqual(["cckp_hd35", "ghsl_pop", "whr_ladder"]);
  });

  it("formats signed and composition dimensions", () => {
    const props = { h3: "85y", iso_a2: "US", admin1_name: "Arizona", population: 2413788, inhabited: true, coverage: 4, jobs_res: "tract", jobs_raw: 0.93, jobs_score: 71, pol_res: "county", pol_lean: -12, race_res: "tract", race_w: 55, race_b: 5, race_h: 31, race_a: 5, race_o: 4, race_maj: "w", wb_res: "none", wb_source: "none", bivar: 0 };
    const m = describeHex(props, "hex5", DIMS, MANIFEST);
    expect(m.resolution).toContain("res 5");
    expect(m.life.find((r) => r.id === "jobs")!.value).toBe("93% employed");
    expect(m.life.find((r) => r.id === "pol")!.value).toBe("R+12 (two-party margin)");
    const race = m.life.find((r) => r.id === "race")!;
    expect(race.majority).toBe("white");
    expect(race.shares!.reduce((a, s) => a + s.pct, 0)).toBe(100);
    expect(m.bivar).toContain("not classified");
    expect(m.wellbeing.value).toBeNull();
    expect(m.sources.map((s) => s.id)).toContain("medsl_county_pres");
  });

  it("formats cost of living by its base (US = 100 for BEA tags, world = 100 nationally) and rent as a monthly dollar amount", () => {
    const us = { h3: "85z", iso_a2: "US", admin1_name: "Arizona", population: 1000, inhabited: true, coverage: 4, cost_res: "county", cost_raw: 112.3, cost_score: 70, rent_res: "county", rent_raw: 1450, rent_score: 55, wb_res: "none", wb_source: "none", bivar: 0 };
    let m = describeHex(us, "hex5", DIMS, MANIFEST);
    expect(m.life.find((r) => r.id === "cost")!.value).toBe("index 112 (US = 100)");
    expect(m.life.find((r) => r.id === "rent")!.value).toBe("$1,450/month (2-bedroom FMR)");
    // a state-level BEA value carries the admin1 tag and is still on the US = 100 base
    m = describeHex({ ...us, cost_res: "admin1", cost_raw: 96.6 }, "hex5", DIMS, MANIFEST);
    expect(m.life.find((r) => r.id === "cost")!.value).toBe("index 97 (US = 100)");
    // outside the US the national ICP / WDI value is on the world = 100 base and rent is absent
    m = describeHex({ ...us, iso_a2: "IS", admin1_name: null, cost_res: "national", cost_raw: 143.2, rent_res: "none", rent_raw: undefined }, "hex5", DIMS, MANIFEST);
    expect(m.life.find((r) => r.id === "cost")!.value).toBe("index 143 (world = 100)");
    expect(m.life.find((r) => r.id === "rent")!.value).toBeNull();
  });
});

describe("hex-level layers in the inspector", () => {
  it("formats the environment rows with their units and the hex / basin tags", () => {
    const props = { h3: "84z", iso_a2: "US", inhabited: true, coverage: 4, care_res: "hex", care_raw: 34.6, care_score: 40, net_res: "hex", net_raw: 118.2, net_score: 80, air_res: "hex", air_raw: 12.34, air_score: 60, trees_res: "hex", trees_raw: 41.2, trees_score: 55, fire_res: "hex", fire_raw: 0.372, fire_score: 70, drought_res: "basin", drought_raw: 3, drought_score: 75, wb_res: "none", wb_source: "none", bivar: 0 };
    const m = describeHex(props, "hex5", DIMS, MANIFEST);
    expect(m.env.map((r) => r.id)).toEqual(["air", "trees", "fire", "drought"]);
    expect(m.life.map((r) => r.id)).toEqual(["jobs", "pol", "race", "cost", "rent", "care", "net"]);
    expect(m.env.find((r) => r.id === "air")!.value).toBe("12.3 µg/m³ PM2.5 (WHO guideline 5)");
    expect(m.env.find((r) => r.id === "trees")!.value).toBe("41% tree cover");
    expect(m.env.find((r) => r.id === "fire")!.value).toBe("0.37% of the area burns per year (2001-2020)");
    expect(m.env.find((r) => r.id === "drought")!).toMatchObject({ value: "drought risk 3 of 4 (medium to high)", res: "basin", score: 75 });
    expect(m.life.find((r) => r.id === "care")!.value).toBe("35 min to the nearest health facility");
    expect(m.life.find((r) => r.id === "net")!.value).toBe("118 Mbps download");
    expect(m.sources.map((s) => s.id)).toContain("acag_pm25");
    // life dimensions without a tag stay "no data"
    expect(m.life.find((r) => r.id === "jobs")!).toMatchObject({ value: null, score: null, res: "none" });
  });

  it("keeps a missing environment layer as no data, never zero", () => {
    const props = { h3: "84z", iso_a2: "US", inhabited: true, coverage: 4, wb_res: "none", wb_source: "none", bivar: 0 };
    const m = describeHex(props, "hex4", DIMS, MANIFEST);
    for (const row of m.env) expect(row).toMatchObject({ value: null, score: null, res: "none" });
  });
});
