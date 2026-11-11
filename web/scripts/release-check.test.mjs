import { describe, expect, it } from "vitest";
import { releaseProblems } from "./release-check.mjs";

const good = {
  fixtures: false,
  bbox: null,
  publish_target: "r2",
  tiles: { hexes: { key: "hexes.0123456789ab.pmtiles" }, hexes_nbhd: { key: "hexes_nbhd.ba9876543210.pmtiles" } },
  dimensions: [{ id: "jobs" }],
};

describe("releaseProblems", () => {
  it("accepts a real r2 release", () => {
    expect(releaseProblems(good)).toEqual([]);
  });

  it("refuses a missing manifest", () => {
    expect(releaseProblems(null)).toHaveLength(1);
  });

  it("refuses fixture, bbox and local builds", () => {
    expect(releaseProblems({ ...good, fixtures: true }).join()).toMatch(/fixture/);
    expect(releaseProblems({ ...good, bbox: [1, 2, 3, 4] }).join()).toMatch(/bbox/);
    expect(releaseProblems({ ...good, publish_target: "local" }).join()).toMatch(/not r2/);
  });

  it("refuses plain archive names and an empty build", () => {
    expect(releaseProblems({ ...good, tiles: { hexes: { key: "hexes.pmtiles" } } }).join()).toMatch(/content-addressed/);
    expect(releaseProblems({ ...good, tiles: {}, dimensions: [] })).toHaveLength(2);
  });
});
