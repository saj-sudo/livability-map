// The map's ground colours per theme (SPEC §9.4, §13.10): land is the page's --paper, so the
// basemap, the plain-background fallback and the page are one surface. A leaf module (no imports
// from the style code) so mapHealth and basemap can both read it.

import type { Theme } from "./theme";

export interface Ground {
  land: string;
  sea: string;
  /** country and region hairlines */
  line: string;
  label: string;
  /** halo behind labels: the land tone, so text reads over hexes */
  halo: string;
  seaLabel: string;
}

export const GROUND: Record<Theme, Ground> = {
  light: { land: "#eef0ec", sea: "#d9dfdc", line: "#aab3ae", label: "#1b2320", halo: "rgba(251,252,250,0.85)", seaLabel: "#6f7b77" },
  dark: { land: "#141a1c", sea: "#0c1113", line: "#3d484b", label: "#e6eae7", halo: "rgba(20,26,28,0.85)", seaLabel: "#7f8b87" },
};
