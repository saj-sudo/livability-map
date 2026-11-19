// The map's own title, like the title of an atlas plate (SPEC §10, §13.50): what is drawn, the
// year, and one line that names the pathway for any projected view, so scenario and horizon are
// always on screen (SPEC §3). Pure; components/PlateTitle.tsx draws it.

import { SCENARIO_LABELS, type ClientManifest } from "./clientManifest";
import { shortName, type DimInfo } from "./dims";
import type { ViewId } from "./url";

export interface Plate {
  title: string;
  sub: string;
}

/** "Moderate pathway (RCP4.5 / SSP2-4.5)" */
export function pathwayLabel(m: Pick<ClientManifest, "scenario">): string {
  const l = SCENARIO_LABELS[m.scenario] ?? m.scenario;
  return l.charAt(0).toUpperCase() + l.slice(1);
}

export function plateTitle(view: ViewId, dims: DimInfo[], manifest: Pick<ClientManifest, "scenario" | "horizon">, presetName: string | null = null): Plate {
  const year = manifest.horizon;
  const path = pathwayLabel(manifest);
  if (view === "exp") return { title: `Climate exposure, ${year}`, sub: `Five hazards combined, with heat counted twice (dry and humid). ${path}.` };
  if (view === "bivar") return { title: `Exposure in ${year} beside wellbeing today`, sub: `Wellbeing colours appear only where the figure is regional or finer. ${path}.` };
  if (view === "priorities") return { title: presetName ? `Fit with ${presetName}` : "Fit with your priorities", sub: `Your weights, applied to every place. Not a ranking. Hazards are for ${year}, ${path.charAt(0).toLowerCase() + path.slice(1)}.` };
  const d = dims.find((x) => x.id === view);
  const name = d ? shortName(d.name) : view;
  if (d?.group === "hazard") return { title: `${name}, ${year}`, sub: `Rank among inhabited places. ${path}.` };
  return { title: `${name} today`, sub: d?.scale === "minmax" ? "Present-day; a score within its source." : "Present-day; rank among inhabited places." };
}
