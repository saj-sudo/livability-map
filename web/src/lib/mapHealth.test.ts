import { describe, expect, it } from "vitest";
import { BASEMAP_HOSTS, classifyError, fallbackStyle, NO_PROBLEMS, noteProblem, problemMessage, supportsWebGL2 } from "./mapHealth";

describe("map health (SPEC §13.40)", () => {
  it("detects WebGL 2 without throwing", () => {
    expect(supportsWebGL2(() => ({ getContext: (k) => (k === "webgl2" ? {} : null) }))).toBe(true);
    expect(supportsWebGL2(() => ({ getContext: () => null }))).toBe(false);
    expect(
      supportsWebGL2(() => {
        throw new Error("no canvas");
      }),
    ).toBe(false);
  });

  it("falls back to a style that requests nothing", () => {
    for (const theme of ["light", "dark"] as const) {
      const s = fallbackStyle(theme);
      expect(s.sources).toEqual({});
      expect(JSON.stringify(s)).not.toMatch(/https?:/);
    }
  });

  it("tells our archives from the basemap", () => {
    const ids = ["hexes", "hexes_nbhd"];
    expect(classifyError({ sourceId: "hexes_nbhd", error: { message: "fetch failed" } }, ids)).toEqual({ kind: "tiles", archive: "hexes_nbhd" });
    expect(classifyError({ sourceId: "openmaptiles" }, ids)).toEqual({ kind: "basemap" });
    expect(classifyError({ error: { message: "AJAXError", url: `https://${BASEMAP_HOSTS[0]}/styles/positron` } }, ids)).toEqual({ kind: "basemap" });
    expect(classifyError({ error: { message: "something else" } }, ids)).toEqual({ kind: "other" });
  });

  it("collects problems once each and words the worst first", () => {
    let p = NO_PROBLEMS;
    expect(problemMessage(p)).toBeNull();
    p = noteProblem(p, { kind: "basemap" });
    expect(noteProblem(p, { kind: "basemap" })).toBe(p);
    expect(problemMessage(p)).toMatch(/background map/);
    p = noteProblem(p, { kind: "tiles", archive: "hexes" });
    p = noteProblem(p, { kind: "tiles", archive: "hexes" });
    expect(p.tiles).toEqual(["hexes"]);
    expect(problemMessage(p)).toMatch(/map data could not be loaded \(hexes\)/);
    expect(noteProblem(p, { kind: "other" })).toBe(p);
  });
});
