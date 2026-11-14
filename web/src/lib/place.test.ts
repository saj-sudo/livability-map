import { describe, expect, it } from "vitest";
import { placeAnnouncement, placeHeader } from "./place";

const m = { title: "Arizona", subtitle: "United States", populationN: 784368, areaKm2: "1,770" };

describe("place panel header", () => {
  it("shows the region and a plain area line after a map click", () => {
    expect(placeHeader(m)).toEqual({ title: "Arizona", subtitle: "United States", line: "About 784,000 people in this ~1,770 km² area" });
  });

  it("keeps the searched city name and moves the region to the subtitle", () => {
    const h = placeHeader(m, { name: "Phoenix", kind: "city" });
    expect(h.title).toBe("Near Phoenix");
    expect(h.subtitle).toBe("Arizona, United States");
  });

  it("does not repeat a searched region that is the hex's own region", () => {
    expect(placeHeader(m, { name: "Arizona", kind: "region" }).title).toBe("Arizona");
    expect(placeHeader(m, { name: "Maricopa", kind: "region" }).title).toBe("In Maricopa");
  });

  it("copes with a hex that has no region", () => {
    const h = placeHeader({ title: "Bangladesh", subtitle: "", populationN: null, areaKm2: "253" }, { name: "Dhaka", kind: "city" });
    expect(h).toEqual({ title: "Near Dhaka", subtitle: "Bangladesh", line: "Population unknown in this ~253 km² area" });
  });

  it("announces the place for screen readers", () => {
    expect(placeAnnouncement({ title: "Near Phoenix", subtitle: "Arizona, United States" })).toBe("Showing details for Near Phoenix, Arizona, United States.");
    expect(placeAnnouncement({ title: "Dhaka", subtitle: "" }, true)).toBe("Comparing with Dhaka.");
  });
});
