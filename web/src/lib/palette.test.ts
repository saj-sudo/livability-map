import { describe, expect, it } from "vitest";
import { PALETTES, paletteFor, scoreBarColor } from "./palette";

describe("score bar colours follow the dimension's direction", () => {
  it("uses the bad (hazard) hue when more is worse and the good hue otherwise, in both themes", () => {
    for (const theme of ["light", "dark"] as const) {
      const pal = paletteFor(theme);
      expect(scoreBarColor(pal, "worse")).toBe(PALETTES[theme].rampHazard[1]);
      expect(scoreBarColor(pal, "better")).toBe(PALETTES[theme].rampGood[1]);
      expect(scoreBarColor(pal, undefined)).toBe(PALETTES[theme].rampGood[1]);
      expect(scoreBarColor(pal, "worse")).not.toBe(scoreBarColor(pal, "better"));
    }
  });
});
