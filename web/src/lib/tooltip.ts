// The hover readout (SPEC §10): place, and one line for the current view. Slim low-zoom tiles
// carry no names or raw values (SPEC §9.2), so the title says to zoom in. Missing data reads
// "no data", never a number (invariant 3).

import { compositeValue, missingCount, priorityBars, type Props } from "./chart";
import { HAZARD_RAW, shortName, type DimInfo } from "./dims";
import type { Picks, Weights } from "./expressions";
import { formatDimRaw, formatHazardRaw, formatPopulation, formatScore } from "./format";
import { countryName } from "./inspect";
import { BIVAR_WORDS } from "./palette";
import type { ViewId } from "./url";

export interface TooltipModel {
  title: string;
  subtitle: string;
  line: string;
  /** bivariate class for the legend highlight; 0 = no data */
  bivar: number;
  /** true when the tile carried no names (zoomed out) */
  slim: boolean;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.length ? v : null);

export function tooltipModel(props: Props, view: ViewId, dims: DimInfo[], weights: Weights, picks: Picks): TooltipModel {
  const admin1 = str(props.admin1_name);
  const iso = str(props.iso_a2);
  const slim = admin1 === null && iso === null;
  const title = slim ? "Zoom in for the place name" : (admin1 ?? countryName(iso));
  const pop = num(props.population);
  const subtitle = slim ? "" : [admin1 ? countryName(iso) : "", pop === null ? "" : formatPopulation(pop)].filter(Boolean).join(", ");
  const bivar = num(props.bivar) ?? 0;

  let line: string;
  if (view === "bivar") {
    line = bivar === 0 ? "no data" : BIVAR_WORDS[bivar];
  } else if (view === "priorities") {
    const bars = priorityBars(props, dims, weights, picks);
    if (!bars.length) line = "no priorities set yet";
    else {
      const c = compositeValue(dims, weights, picks, props);
      const { missing, total } = missingCount(bars);
      line = c === null ? "no data for any of your priorities" : `matches your priorities ${formatScore(c)}${missing ? ` (${missing} of ${total} missing here)` : ""}`;
    }
  } else {
    const d = dims.find((x) => x.id === view);
    const score = num(props[`${view}_score`]);
    const ok = props[`${view}_ok`] !== false && props[`${view}_res`] !== "none";
    const label = d ? shortName(d.name) : view;
    if (score === null || !ok) line = `${label}: no data`;
    else {
      const raw = d?.group === "hazard" ? formatHazardRaw(view, num(props[HAZARD_RAW[view]?.attr ?? `${view}_raw`])) : d ? formatDimRaw(d, num(props[`${view}_raw`]), str(props[`${view}_res`]) ?? "") : null;
      line = `${label}: ${formatScore(score)}${raw ? `, ${raw}` : ""}`;
    }
  }
  return { title, subtitle, line, bivar, slim };
}
