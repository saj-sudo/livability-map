// Colour measures for the palette guard tests (SPEC §9.3): OKLab lightness and distance, and
// protan / deutan simulation (Viénot, Brettel and Mollon 1999, in linear RGB). Test-support code;
// nothing in the app imports it.

export type RGB = [number, number, number];

export function hexToRgb(hex: string): RGB {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as RGB;
}

const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

export function linear(hex: string): RGB {
  return hexToRgb(hex).map(toLinear) as RGB;
}

/** OKLab [L, a, b] from linear sRGB (Ottosson 2020). */
export function oklabFromLinear([r, g, b]: RGB): RGB {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

export const oklab = (hex: string): RGB => oklabFromLinear(linear(hex));
export const lightness = (hex: string): number => oklab(hex)[0];

const dist = (a: RGB, b: RGB) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
/** Euclidean distance in OKLab; about 0.02 is a just-noticeable difference for adjacent patches. */
export const deltaE = (a: string, b: string): number => dist(oklab(a), oklab(b));

const CVD: Record<"protan" | "deutan", number[][]> = {
  protan: [
    [0.11238, 0.88762, 0],
    [0.11238, 0.88762, 0],
    [0.00401, -0.00401, 1],
  ],
  deutan: [
    [0.29275, 0.70725, 0],
    [0.29275, 0.70725, 0],
    [-0.02234, 0.02234, 1],
  ],
};

/** Distance between two colours as a protanope or deuteranope would see them. */
export function deltaECvd(a: string, b: string, kind: "protan" | "deutan"): number {
  const sim = (hex: string): RGB => {
    const c = linear(hex);
    return oklabFromLinear(CVD[kind].map((row) => Math.min(1, Math.max(0, row[0] * c[0] + row[1] * c[1] + row[2] * c[2]))) as RGB);
  };
  return dist(sim(a), sim(b));
}
