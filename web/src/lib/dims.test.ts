import { describe, expect, it } from "vitest";
import { chipFor, DIM_ORDER, dimensionsFrom, envDims, isAvailable, lifeDims, resLabel, unitsFrom } from "./dims";
import { EMPTY_MANIFEST, type Manifest, type ManifestDimension } from "./manifest";

// shaped like the real manifest.json: `coverage` holds per-res tag counts (the registry's
// domain list is overwritten), and `domains` holds per-res domain counts
const dim = (id: string, extra: Partial<ManifestDimension> = {}): ManifestDimension =>
  ({ id, name: id, group: "life", kind: "score", higher_is: "better", coverage: [], sources: [], scale: "percentile", joiners: [], note: "", ...extra }) as ManifestDimension;

describe("dimension registry from the manifest", () => {
  it("reads coverage chips from the scoring domains, not the per-res counts", () => {
    const jobs = dim("jobs", { coverage: { "4": { national: 39457, admin1: 6587, tract: 4186, none: 706 } } as never, domains: { "4": { global: 39457, oecd: 6587, us: 4186 } } });
    expect(chipFor(jobs)).toBe("Global / OECD / US");
    const transit = dim("transit", { coverage: { "4": { tract: 777, none: 50159 } } as never, domains: { "4": { us: 777 } } });
    expect(chipFor(transit)).toBe("US only");
    const heat = dim("heat", { group: "hazard", coverage: ["global"] });
    expect(chipFor(heat)).toBe("Global");
    // no data yet (pol before MEDSL): fall back to the joiners' domains
    const pol = dim("pol", { kind: "signed", coverage: { "4": { none: 50936 } } as never, domains: {}, joiners: [{ source: "medsl", joiner: "area_weighted_overlay", res: "county", field: "lean", domain: "us", label: "medsl" }] });
    expect(chipFor(pol)).toBe("US only");
  });

  it("marks a dimension unavailable when no hex carries a value", () => {
    expect(isAvailable(dim("pol", { coverage: { "4": { none: 50936 } } as never }))).toBe(false);
    expect(isAvailable(dim("transit", { coverage: { "4": { tract: 777, none: 50159 } } as never }))).toBe(true);
    expect(isAvailable(dim("heat", { coverage: ["global"] }))).toBe(true);
  });

  it("orders by DIM_ORDER and appends new manifest dimensions after it", () => {
    const m: Manifest = { ...EMPTY_MANIFEST, hazards: [dim("heat", { group: "hazard" })], dimensions: [dim("rent", { name: "Rent" }), dim("wb", { group: "wellbeing" }), dim("jobs")] };
    const ids = dimensionsFrom(m).map((d) => d.id);
    expect(ids).toEqual(["heat", "wb", "jobs", "rent"]);
    expect(ids.slice(0, 3).every((id) => (DIM_ORDER as readonly string[]).includes(id))).toBe(true);
    expect(dimensionsFrom(m).find((d) => d.id === "rent")!.available).toBe(true);
  });

  it("falls back to the built-in registry when the manifest is empty", () => {
    const dims = dimensionsFrom(EMPTY_MANIFEST);
    expect(dims.map((d) => d.id)).toEqual([...DIM_ORDER]);
    expect(dims.find((d) => d.id === "transit")!.chip).toBe("US only");
  });

  it("appends new dimensions to DIM_ORDER so old `w=` links keep their meaning", () => {
    // the first fourteen slots are frozen: hazards, wellbeing, then the Session 4 life dimensions
    expect(DIM_ORDER.slice(0, 14)).toEqual(["heat", "rflood", "cflood", "wstress", "wb", "jobs", "transit", "school", "lgbtq", "pol", "race", "incmix", "house", "health"]);
    expect(DIM_ORDER.slice(14, 16)).toEqual(["cost", "rent"]);
    expect(DIM_ORDER.slice(16)).toEqual(["care", "air", "trees", "net", "fire", "drought"]);
    expect(new Set(DIM_ORDER).size).toBe(DIM_ORDER.length);
  });

  it("reads units per resolution tag from the manifest joiners, first joiner per tag winning", () => {
    const cost = dim("cost", { unit: "index", decimals: 0, joiners: [
      { source: "bea_rpp_metro", joiner: "polygon_centroid", res: "county", field: "rpp_all", domain: "us", label: "bea", unit: "index (US = 100)", multiply: 1, decimals: 0 },
      { source: "wb_icp_pli", joiner: "iso_lookup", res: "national", field: "pli_household", domain: "global", label: "icp", unit: "index (world = 100)", multiply: 1, decimals: 0 },
      { source: "wb_gdp_pli", joiner: "iso_lookup", res: "national", field: "pli_gdp", domain: "global", label: "wdi", unit: "should not win", multiply: 1, decimals: 0 },
    ] });
    const u = unitsFrom(cost);
    expect(u["*"]).toEqual({ unit: "index", multiply: 1, decimals: 0 });
    expect(u.county.unit).toBe("index (US = 100)");
    expect(u.national.unit).toBe("index (world = 100)");
    expect(dimensionsFrom({ ...EMPTY_MANIFEST, dimensions: [cost] })[0].units!.national.unit).toBe("index (world = 100)");
    expect(unitsFrom(dim("plain"))).toEqual({});
  });

  it("keeps the environment group apart from the life dimensions and labels the new tags", () => {
    const dims = dimensionsFrom(EMPTY_MANIFEST);
    expect(envDims(dims).map((d) => d.id)).toEqual(["air", "trees", "fire", "drought"]);
    expect(lifeDims(dims).map((d) => d.id)).toContain("care");
    expect(lifeDims(dims).map((d) => d.id)).not.toContain("air");
    expect(dims.find((d) => d.id === "cost")!.higher_is).toBe("worse"); // a higher price level is worse for the person
    expect(dims.find((d) => d.id === "rent")!.chip).toBe("US only");
    expect(resLabel("hex")).toBe("this hex");
    expect(resLabel("basin")).toBe("sub-basin");
    expect(resLabel("weird")).toBe("weird");
  });
});
