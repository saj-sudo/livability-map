// Diagonal hatch pattern for reduced-confidence hexes (SPEC §9.3, decision §13.4), generated
// in code so no sprite or image asset is needed. Seamless because size is a multiple of the
// stripe period.
import { HATCH_RGBA } from "./palette";

export interface RawImage {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

export function hatchImage(size = 16, rgba: [number, number, number, number] = HATCH_RGBA, period = 8, width = 2): RawImage {
  const data = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      if ((x + y) % period < width) data.set(rgba, (y * size + x) * 4);
    }
  }
  return { width: size, height: size, data };
}
