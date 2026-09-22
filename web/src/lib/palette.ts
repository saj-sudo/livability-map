// Colours (SPEC §9.3, §13.10). One palette per theme; the map, the legend and the inspector all
// read from PALETTES so a theme change re-colours everything consistently.
//
// Bivariate classes follow pipeline/scoring.py bivariate_class:
// class = 1 + exposure tercile + 3 x wellbeing tercile, 0 when either side is missing.
// Columns = exposure (low -> high, left to right) in a warm red; rows = wellbeing (low -> high,
// bottom to top) in a cool teal; both high is a dark mauve (light) / light mauve (dark).
// Light grid: Joshua Stevens' red/blue scheme. Dark grid: derived in OKLCH (scripts/bivar_dark.mjs)
// so lightness climbs with exposure + wellbeing; rows and columns validated monotone and the
// corner cells validated separable under protan/deutan simulation (dataviz validator).

import type { Theme } from "./theme";

export interface Palette {
  bivar: Record<number, string>;
  /** no data (never 0; invariant 3) */
  grey: string;
  /** sequential ramps as 3 stops at scores 0, 50, 100 */
  rampHazard: string[];
  rampGood: string[];
  rampWellbeing: string[];
  rampPriority: string[];
  /** hex seam: paper-toned so the mesh recedes */
  outline: string;
  /** dashed outline for national-fallback wellbeing */
  national: string;
  hover: string;
  selected: string;
  /** wide line under the selection so it reads on every fill colour */
  halo: string;
  hatch: [number, number, number, number];
}

export const PALETTES: Record<Theme, Palette> = {
  light: {
    bivar: {
      1: "#e8e8e8", // low exposure, low wellbeing
      2: "#e4acac",
      3: "#c85a5a", // high exposure, low wellbeing
      4: "#b0d5df",
      5: "#ad9ea5",
      6: "#985356",
      7: "#64acbe", // low exposure, high wellbeing
      8: "#627f8c",
      9: "#574249", // high exposure, high wellbeing
    },
    grey: "#cfd3cf",
    rampHazard: ["#f6e7dc", "#c85a5a", "#5a1d1d"],
    rampGood: ["#e6f0e4", "#63a95f", "#1f4d24"],
    rampWellbeing: ["#e3eef2", "#64acbe", "#1f4b5c"],
    rampPriority: ["#e6e6f2", "#7f76c2", "#2f2a66"],
    outline: "rgba(238,240,236,0.5)",
    national: "rgba(27,35,32,0.35)",
    hover: "#1b2320",
    selected: "#1b2320",
    halo: "#fbfcfa",
    hatch: [27, 35, 32, 140],
  },
  dark: {
    bivar: {
      1: "#494e4e",
      2: "#99605e",
      3: "#df6768",
      4: "#457b88",
      5: "#9d8c9b",
      6: "#e39385",
      7: "#21a3bc",
      8: "#80b4c5",
      9: "#dfb4da",
    },
    grey: "#2c3437",
    rampHazard: ["#4a2a28", "#c85a5a", "#f2c2b3"],
    rampGood: ["#22402a", "#57a05c", "#c6e6c4"],
    rampWellbeing: ["#1f3f4a", "#4a9fb5", "#bfe3ea"],
    rampPriority: ["#2c2a5a", "#7a72c4", "#d3d0ee"],
    outline: "rgba(20,26,28,0.55)",
    national: "rgba(230,234,231,0.35)",
    hover: "#e6eae7",
    selected: "#e6eae7",
    halo: "#141a1c",
    hatch: [230, 234, 231, 120],
  },
};

export const paletteFor = (theme: Theme | undefined): Palette => PALETTES[theme ?? "light"];

// aliases for the light palette, kept so callers without a theme still work
export const BIVAR = PALETTES.light.bivar;
export const GREY = PALETTES.light.grey;
export const HATCH_RGBA = PALETTES.light.hatch;
export const RAMP_HAZARD = PALETTES.light.rampHazard;
export const RAMP_GOOD = PALETTES.light.rampGood;
export const RAMP_WELLBEING = PALETTES.light.rampWellbeing;
export const RAMP_PRIORITY = PALETTES.light.rampPriority;

export const BIVAR_WORDS: Record<number, string> = {
  0: "not classified (missing exposure or wellbeing)",
  1: "low exposure, low wellbeing",
  2: "medium exposure, low wellbeing",
  3: "high exposure, low wellbeing",
  4: "low exposure, medium wellbeing",
  5: "medium exposure, medium wellbeing",
  6: "high exposure, medium wellbeing",
  7: "low exposure, high wellbeing",
  8: "medium exposure, high wellbeing",
  9: "high exposure, high wellbeing",
};

/** Categorical colours for the composition shares (fixed order w, b, h, a, o; dataviz rule 1). */
export const SHARE_COLORS: Record<Theme, string[]> = {
  light: ["#7f76c2", "#63a95f", "#d98a3d", "#3d7f93", "#9a9a9a"],
  dark: ["#a9a3dc", "#8cc78e", "#e5a86a", "#7fc5d6", "#8a9297"],
};
