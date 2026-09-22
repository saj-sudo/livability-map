// Derive the dark-theme bivariate grid in OKLCH so lightness climbs with (exposure + wellbeing)
// while hue keeps the light grid's meaning: red = exposure, teal = wellbeing, mauve = both.
// Run: node scripts/bivar_dark.mjs  -> prints the 9 hexes (used once; result pasted into palette.ts)

function oklchToHex(L, C, h) {
  const a = C * Math.cos((h * Math.PI) / 180);
  const b = C * Math.sin((h * Math.PI) / 180);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3;
  const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bb = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;
  const gamma = (x) => (x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055);
  const to = (x) => Math.max(0, Math.min(255, Math.round(gamma(x) * 255)));
  return "#" + [r, g, bb].map((x) => to(x).toString(16).padStart(2, "0")).join("");
}

// [L, C, hue] per cell, class = 1 + exposure + 3 * wellbeing
const RED = 22, TEAL = 215, MAUVE = 330;
const cells = {
  1: [0.42, 0.006, 200], // low, low: near-surface grey
  2: [0.55, 0.075, RED],
  3: [0.66, 0.15, RED], // high exposure, low wellbeing
  4: [0.55, 0.06, TEAL],
  5: [0.66, 0.03, MAUVE], // middle: quiet mauve-grey
  6: [0.74, 0.10, RED + 8],
  7: [0.66, 0.11, TEAL], // low exposure, high wellbeing
  8: [0.74, 0.06, TEAL + 5],
  9: [0.82, 0.07, MAUVE], // both high: light mauve
};
const out = {};
for (const k of Object.keys(cells)) out[k] = oklchToHex(...cells[k]);
console.log(JSON.stringify(out, null, 1));
console.log(Object.values(out).join(","));
