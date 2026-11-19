import { describe, expect, it } from "vitest";
import { deltaE, deltaECvd, lightness } from "./colorMath";
import { GROUND } from "./ground";
import { exposureOnly, PALETTES } from "./palette";

// Guard tests that measure what the palette comments claim (SPEC §9.3). Distances are Euclidean
// in OKLab; about 0.02 is a just-noticeable difference between adjacent patches.
const THEMES = ["light", "dark"] as const;
/** no-data grey to any data colour: at least two just-noticeable differences */
const MIN_FROM_GREY = 0.04;
/** corner cells of the 3x3 grid as a protanope or deuteranope sees them */
const MIN_CORNERS_CVD = 0.08;
/** exposure-only colours to every cell of the 3x3 grid */
const MIN_ONLY_FROM_GRID = 0.06;

const ROWS = [
  [1, 2, 3],
  [4, 5, 6],
  [7, 8, 9],
];
const COLS = [
  [1, 4, 7],
  [2, 5, 8],
  [3, 6, 9],
];
/** strictly one direction: every step moves the same way */
const monotone = (xs: number[]): boolean => xs.every((x, i) => i === 0 || Math.sign(x - xs[i - 1]) === Math.sign(xs[1] - xs[0])) && xs[1] !== xs[0];

describe("palette guards (SPEC §9.3)", () => {
  it("lightness is monotone along every row and column of the bivariate grid", () => {
    for (const t of THEMES) {
      for (const line of [...ROWS, ...COLS]) expect(monotone(line.map((k) => lightness(PALETTES[t].bivar[k]))), `${t} ${line}`).toBe(true);
    }
  });

  it("every ramp is lightness-monotone and its high end stands out most from the ground", () => {
    for (const t of THEMES) {
      const p = PALETTES[t];
      const land = lightness(GROUND[t].land);
      for (const ramp of [p.rampExposure, p.exposureOnly, p.rampHazard, p.rampGood, p.rampWellbeing, p.rampPriority]) {
        const L = ramp.map(lightness);
        expect(monotone(L), `${t} ${ramp}`).toBe(true);
        expect(Math.abs(L[L.length - 1] - land)).toBeGreaterThan(Math.abs(L[0] - land));
      }
      // the same holds for the grid: "both high" is further from the ground than "both low"
      expect(Math.abs(lightness(p.bivar[9]) - land)).toBeGreaterThan(Math.abs(lightness(p.bivar[1]) - land));
    }
  });

  it("the no-data grey is never close to a data colour, or to the ground", () => {
    for (const t of THEMES) {
      const p = PALETTES[t];
      const data = [...Object.values(p.bivar), ...p.rampExposure, ...p.exposureOnly, ...p.rampHazard, ...p.rampGood, ...p.rampWellbeing, ...p.rampPriority, GROUND[t].land];
      for (const c of data) expect(deltaE(p.grey, c), `${t} grey ${p.grey} vs ${c}`).toBeGreaterThanOrEqual(MIN_FROM_GREY);
    }
  });

  it("the corner cells stay separable under protan and deutan simulation", () => {
    const corners = [1, 3, 7, 9];
    for (const t of THEMES) {
      for (const kind of ["protan", "deutan"] as const) {
        for (const [i, a] of corners.entries()) for (const b of corners.slice(i + 1)) expect(deltaECvd(PALETTES[t].bivar[a], PALETTES[t].bivar[b], kind), `${t} ${kind} ${a}-${b}`).toBeGreaterThanOrEqual(MIN_CORNERS_CVD);
      }
    }
  });

  it("exposure-only colours cannot be mistaken for a cell of the grid, least of all the low-wellbeing row", () => {
    for (const t of THEMES) {
      const p = PALETTES[t];
      expect(exposureOnly(p)).toHaveLength(3);
      for (const c of exposureOnly(p)) for (const k of [1, 2, 3, 4, 5, 6, 7, 8, 9]) expect(deltaE(c, p.bivar[k]), `${t} ${c} vs class ${k}`).toBeGreaterThanOrEqual(MIN_ONLY_FROM_GRID);
    }
  });

  it("the default view's ramp has five steps", () => {
    for (const t of THEMES) expect(PALETTES[t].rampExposure).toHaveLength(5);
  });
});
