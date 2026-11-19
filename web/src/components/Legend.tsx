"use client";

// The key (SPEC §9.3): docked on the map on a wide screen, one line in the sheet's peek on a
// phone. A ramp with its ends in words for one-variable views; the 3x3 grid plus the
// exposure-only row for the bivariate view. It names variables and never captions a corner with
// a verdict (§3). One rule in both themes: the end that stands out from the ground is "more".

import { useTheme } from "./useTheme";
import { shortName, type DimInfo } from "../lib/dims";
import { rampFor } from "../lib/expressions";
import { BIVAR_WORDS, exposureOnly, paletteFor, type Palette } from "../lib/palette";
import type { ViewId } from "../lib/url";

interface Props {
  view: ViewId;
  dims: DimInfo[];
  conf: boolean;
  /** bivariate class of the hovered hex (0 = no data, -1 = exposure only), lights its cell */
  highlight?: number | null;
}

// grid rows top to bottom = wellbeing high to low; columns left to right = exposure low to high
const GRID = [
  [7, 8, 9],
  [4, 5, 6],
  [1, 2, 3],
];

export interface KeyModel {
  title: string;
  low: string;
  high: string;
  /** discrete steps, or a three-stop gradient */
  steps?: string[];
  gradient?: string[];
}

/** What the ramp shows for a one-variable view (null for the bivariate grid). */
export function keyModel(view: ViewId, dims: DimInfo[], pal: Palette): KeyModel | null {
  if (view === "bivar") return null;
  if (view === "exp") return { title: "Projected exposure", low: "less exposed", high: "more exposed", steps: pal.rampExposure };
  if (view === "priorities") return { title: "Fit with your weights", low: "weaker fit", high: "stronger fit", gradient: pal.rampPriority };
  const dim = dims.find((d) => d.id === view);
  if (!dim) return { title: view, low: "lowest", high: "highest", gradient: pal.rampGood };
  const more = dim.group === "hazard" || dim.higher_is === "worse";
  const ranked = dim.scale !== "minmax";
  return { title: `${shortName(dim.name)}, ${ranked ? "rank among inhabited places" : "score within its source"}`, low: more ? "least" : "lowest", high: more ? "most" : "highest", gradient: rampFor(dim, pal) };
}

function RampBar({ k, className }: { k: KeyModel; className?: string }) {
  if (k.steps) {
    return (
      <span className={`grid ${className ?? ""}`} style={{ gridTemplateColumns: `repeat(${k.steps.length}, 1fr)` }} aria-hidden="true">
        {k.steps.map((c) => (
          <i key={c} className="block h-full" style={{ background: c }} />
        ))}
      </span>
    );
  }
  return <span className={`block ${className ?? ""}`} style={{ background: `linear-gradient(90deg, ${(k.gradient ?? []).join(", ")})` }} aria-hidden="true" />;
}

const hatchCss = (pal: Palette, gap: number) => `repeating-linear-gradient(45deg, rgba(${pal.hatch[0]},${pal.hatch[1]},${pal.hatch[2]},0.6) 0 2px, transparent 2px ${gap}px)`;

/** The full key, docked on the map. */
export default function MapKey({ view, dims, conf, highlight }: Props) {
  const [theme] = useTheme();
  const pal = paletteFor(theme);
  const k = keyModel(view, dims, pal);
  const lit = highlight ?? null;
  const only = exposureOnly(pal);
  return (
    <div className="w-[17rem] space-y-2 rounded-panel border border-rule bg-panel-solid p-3 text-fine" data-testid="map-key" aria-label="Colour key" role="group">
      {k ? (
        <div>
          <div className="mb-1.5 font-serif text-[15px] leading-tight text-ink">{k.title}</div>
          <RampBar k={k} className="h-3.5 w-full" />
          <div className="mt-1 flex justify-between text-muted">
            <span>{k.low}</span>
            <span>{k.high}</span>
          </div>
        </div>
      ) : (
        <div>
          <div className="mb-1.5 font-serif text-[15px] leading-tight text-ink">Exposure beside wellbeing</div>
          <div className="flex items-stretch gap-2">
            <div className="flex w-4 items-center justify-center" aria-hidden="true">
              <span className="whitespace-nowrap text-muted" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
                higher wellbeing →
              </span>
            </div>
            <div className="w-[7rem]">
              <div
                className="grid grid-cols-3 gap-[2px]"
                role="img"
                aria-label="Colour key: rows are wellbeing, from the lowest third of places at the bottom to the highest third at the top; columns are climate exposure, from the lowest third on the left to the highest third on the right"
              >
                {GRID.flat().map((c) => (
                  <div key={c} className="aspect-square w-full rounded-[2px] transition-[box-shadow] duration-150" style={{ background: pal.bivar[c], boxShadow: lit === c ? `0 0 0 2px var(--panel-solid), 0 0 0 4px var(--ink)` : undefined }} title={BIVAR_WORDS[c]} />
                ))}
              </div>
              <div className="mt-1 whitespace-nowrap text-muted">more climate exposure →</div>
            </div>
          </div>
          <div className="mt-2 flex items-center gap-2 text-muted">
            <span className="grid h-3 w-12 shrink-0 grid-cols-3" style={{ boxShadow: lit === -1 ? `0 0 0 2px var(--panel-solid), 0 0 0 4px var(--ink)` : undefined }} aria-hidden="true">
              {only.map((c) => (
                <i key={c} className="block h-full" style={{ background: c }} />
              ))}
            </span>
            exposure only: wellbeing here is one national figure
          </div>
          <div className="mt-1 flex items-center gap-2 text-muted">
            <span className="inline-block h-0 w-12 shrink-0 border-t-2 border-dashed" style={{ borderColor: pal.border }} aria-hidden="true" />
            country border
          </div>
          <p className="mt-1.5 min-h-[1.3em] text-ink">{lit === null ? "" : lit === 0 ? "no data here" : lit === -1 ? "exposure only here" : BIVAR_WORDS[lit]}</p>
        </div>
      )}
      <ul className="space-y-1 text-muted">
        <li className="flex items-center gap-2">
          <span className="inline-block h-3 w-5 shrink-0 rounded-[2px]" style={{ background: pal.grey }} aria-hidden="true" />
          no data, never shown as zero
        </li>
        {conf && (
          <li className="flex items-center gap-2">
            <span className="inline-block h-3 w-5 shrink-0 rounded-[2px]" style={{ background: hatchCss(pal, 6) }} aria-hidden="true" />
            some hazard layers missing
          </li>
        )}
      </ul>
    </div>
  );
}

/** The key in one line, for the phone sheet at its peek height. */
export function CompactLegend({ view, dims, conf }: { view: ViewId; dims: DimInfo[]; conf: boolean }) {
  const [theme] = useTheme();
  const pal = paletteFor(theme);
  const k = keyModel(view, dims, pal);
  return (
    <div className="flex items-center gap-3 text-fine leading-tight text-muted" data-testid="compact-legend">
      {k ? (
        <span className="min-w-0 flex-1">
          <span className="block truncate text-ink">{k.title}</span>
          <span className="mt-0.5 flex items-center gap-1.5">
            <span className="shrink-0">{k.low}</span>
            <RampBar k={k} className="h-2.5 flex-1" />
            <span className="shrink-0">{k.high}</span>
          </span>
        </span>
      ) : (
        <>
          <span className="grid w-[30px] shrink-0 grid-cols-3 gap-px" role="img" aria-label="Colour key: redder means more climate exposure, bluer means higher wellbeing">
            {GRID.flat().map((c) => (
              <i key={c} className="block aspect-square" style={{ background: pal.bivar[c] }} />
            ))}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-ink">Redder: more climate exposure</span>
            <span className="block text-ink">Bluer: higher wellbeing, where it is local</span>
          </span>
        </>
      )}
      <span className="flex shrink-0 flex-col gap-0.5">
        <span className="flex items-center gap-1">
          <i className="inline-block h-2.5 w-3.5 rounded-[2px]" style={{ background: pal.grey }} aria-hidden="true" />
          no data
        </span>
        {conf && (
          <span className="flex items-center gap-1">
            <i className="inline-block h-2.5 w-3.5 rounded-[2px]" style={{ background: hatchCss(pal, 5) }} aria-hidden="true" />
            some missing
          </span>
        )}
      </span>
    </div>
  );
}
