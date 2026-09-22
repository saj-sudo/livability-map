import { describe, expect, it } from "vitest";
import { chipFor, DIM_ORDER, dimensionsFrom, isAvailable } from "./dims";
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
});
