// Colours (SPEC §9.3). Bivariate classes follow pipeline/scoring.py bivariate_class:
// class = 1 + exposure tercile + 3 x wellbeing tercile, 0 when either side is missing.
// Rows = wellbeing (low -> high, bottom to top), columns = exposure (low -> high).

export const GREY = "#d4d4d4"; // no data (never 0; invariant 3)
export const HATCH_RGBA: [number, number, number, number] = [40, 40, 40, 150];

// Joshua Stevens-style 3x3 palette: purple axis = wellbeing, teal axis = exposure
export const BIVAR: Record<number, string> = {
  1: "#e8e8e8", // low exposure, low wellbeing
  2: "#ace4e4",
  3: "#5ac8c8", // high exposure, low wellbeing
  4: "#dfb0d6",
  5: "#a5add3",
  6: "#5698b9",
  7: "#be64ac", // low exposure, high wellbeing
  8: "#8c62aa",
  9: "#3b4994", // high exposure, high wellbeing
};

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

// sequential ramps (0, 50, 100)
export const RAMP_HAZARD = ["#fff7ec", "#fc8d59", "#7f0000"]; // more hazard = darker red
export const RAMP_GOOD = ["#f7fcf5", "#74c476", "#00441b"]; // more of a good thing = darker green
export const RAMP_WELLBEING = ["#fcfbfd", "#9e9ac8", "#3f007d"];
export const RAMP_PRIORITY = ["#fff5eb", "#fd8d3c", "#7f2704"]; // composite match 0..100
