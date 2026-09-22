import { describe, expect, it } from "vitest";
import { foldKey, parseGazetteer, rankPlaces, zoomFor, type GazetteerFile, type Place } from "./search";

// the compact on-disk form: [name, key, kind, iso2, lat, lng, pop]
const RAW: GazetteerFile = {
  v: 1,
  built: "2026-09-22",
  places: [
    ["Denver", "denver", "c", "US", 39.74, -104.98, 2900000],
    ["Colorado", "colorado", "r", "US", 39.0, -105.5, null],
    ["Lagos", "lagos", "c", "NG", 6.45, 3.4, 13400000],
    ["Lagos", "lagos", "r", "NG", 6.6, 3.5, null],
    ["Lagos", "lagos", "c", "PT", 37.1, -8.67, 22000],
    ["São Paulo", "sao paulo", "c", "BR", -23.55, -46.63, 22000000],
    ["St. Louis", "st louis", "c", "US", 38.63, -90.2, 2200000],
    ["Saint-Étienne", "saint etienne", "c", "FR", 45.43, 4.39, 400000],
    ["Bayern", "bayern", "r", "DE", 48.8, 11.5, null],
    ["Bayamón", "bayamon", "c", "PR", 18.4, -66.15, 180000],
    ["New Delhi", "new delhi", "c", "IN", 28.6, 77.2, 30000000],
    ["Delhi", "delhi", "r", "IN", 28.7, 77.1, null],
  ],
};
const PLACES: Place[] = parseGazetteer(RAW);

describe("place search (bundled gazetteer, no third-party request)", () => {
  it("folds accents, case and punctuation into the search key", () => {
    expect(foldKey("São Paulo")).toBe("sao paulo");
    expect(foldKey("Saint-Étienne")).toBe("saint etienne");
    expect(foldKey("  ST.  Louis ")).toBe("st louis");
    expect(foldKey("Bayamón")).toBe("bayamon");
  });

  it("parses the compact form and keeps kinds and populations", () => {
    expect(PLACES).toHaveLength(12);
    const denver = PLACES.find((p) => p.name === "Denver")!;
    expect(denver).toMatchObject({ kind: "city", iso2: "US", pop: 2900000 });
    expect(PLACES.find((p) => p.name === "Colorado")!.pop).toBeNull();
  });

  it("returns nothing for an empty query and at most the limit", () => {
    expect(rankPlaces("", PLACES)).toEqual([]);
    expect(rankPlaces("  ", PLACES)).toEqual([]);
    expect(rankPlaces("a", PLACES, 3)).toHaveLength(3);
  });

  it("ranks exact, then prefix, then word-prefix, then substring", () => {
    const names = rankPlaces("delhi", PLACES).map((p) => `${p.name}/${p.kind}`);
    expect(names[0]).toBe("Delhi/region"); // exact key beats the prefix-of-a-word match
    expect(names).toContain("New Delhi/city");
    expect(rankPlaces("new d", PLACES)[0].name).toBe("New Delhi");
    expect(rankPlaces("louis", PLACES)[0].name).toBe("St. Louis"); // word prefix
    expect(rankPlaces("aul", PLACES)[0].name).toBe("São Paulo"); // substring
  });

  it("puts the city before the region of the same name, bigger cities first", () => {
    const lagos = rankPlaces("lagos", PLACES);
    expect(lagos.map((p) => `${p.iso2}/${p.kind}`)).toEqual(["NG/city", "PT/city", "NG/region"]);
  });

  it("matches accented queries and typed accents", () => {
    expect(rankPlaces("sao", PLACES)[0].name).toBe("São Paulo");
    expect(rankPlaces("Étienne", PLACES)[0].name).toBe("Saint-Étienne");
  });

  it("zooms closer for a city than for a region", () => {
    expect(zoomFor(PLACES.find((p) => p.name === "Denver")!)).toBeGreaterThan(zoomFor(PLACES.find((p) => p.name === "Colorado")!));
  });
});
