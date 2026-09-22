// Legend (SPEC §9.3, §10): the 3x3 bivariate grid is the piece the whole map is read against,
// so it is drawn large, with its axes as sentences, the corner meanings spelled out and the
// hovered hex's cell lit; single layers and the priorities composite get a ticked ramp; the
// keys for no data, reduced confidence and national fallback follow.

import type { DimInfo } from "../lib/dims";
import { rampFor } from "../lib/expressions";
import { BIVAR_WORDS, paletteFor } from "../lib/palette";
import type { Theme } from "../lib/theme";
import type { ViewId } from "../lib/url";

interface Props {
  view: ViewId;
  dims: DimInfo[];
  conf: boolean;
  theme?: Theme;
  /** bivariate class of the hovered hex (0 = no data), lights its cell */
  highlight?: number | null;
}

// grid rows top to bottom = wellbeing high to low; columns left to right = exposure low to high
const GRID = [
  [7, 8, 9],
  [4, 5, 6],
  [1, 2, 3],
];

function Ramp({ colors, low, high, label }: { colors: string[]; low: string; high: string; label: string }) {
  return (
    <div>
      <div className="mb-1 text-[13px]">{label}</div>
      <div className="h-3 w-full rounded-[3px]" style={{ background: `linear-gradient(90deg, ${colors[0]}, ${colors[1]}, ${colors[2]})` }} aria-hidden="true" />
      <div className="mt-0.5 flex justify-between text-[11px] text-muted" aria-hidden="true">
        {[0, 25, 50, 75, 100].map((t) => (
          <span key={t} className="relative w-px bg-rule" style={{ height: 4 }} />
        ))}
      </div>
      <div className="flex justify-between text-[11px] text-muted">
        <span>{low}</span>
        <span>50</span>
        <span>{high}</span>
      </div>
    </div>
  );
}

export default function Legend({ view, dims, conf, theme, highlight }: Props) {
  const pal = paletteFor(theme);
  const dim = dims.find((d) => d.id === view);
  const lit = highlight ?? null;
  return (
    <div className="space-y-3 text-[12px]">
      {view === "bivar" && (
        <div>
          <div className="mb-1.5 font-serif text-[15px]">Climate exposure × wellbeing</div>
          <div className="flex items-stretch gap-2">
            <div className="flex w-4 items-center justify-center" aria-hidden="true">
              <span className="whitespace-nowrap text-[11px] text-muted" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
                higher wellbeing →
              </span>
            </div>
            <div className="w-[8.75rem]">
              <div
                className="grid grid-cols-3 gap-[2px]"
                role="img"
                aria-label="Bivariate legend: rows are wellbeing terciles from low at the bottom to high at the top; columns are climate exposure terciles from low on the left to high on the right"
              >
                {GRID.flat().map((k) => (
                  <div
                    key={k}
                    className="aspect-square w-full rounded-[2px] transition-[box-shadow] duration-150"
                    style={{ background: pal.bivar[k], boxShadow: lit === k ? `0 0 0 2px var(--panel-solid), 0 0 0 4px var(--ink)` : undefined }}
                    title={BIVAR_WORDS[k]}
                  />
                ))}
              </div>
              <div className="mt-1 whitespace-nowrap text-[11px] text-muted">more climate exposure →</div>
            </div>
          </div>
          <div className="mt-1.5 grid grid-cols-2 gap-x-2 text-[11px] text-muted">
            <span className="flex items-center gap-1.5">
              <i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: pal.bivar[7] }} aria-hidden="true" />
              safe and thriving
            </span>
            <span className="flex items-center gap-1.5">
              <i className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: pal.bivar[3] }} aria-hidden="true" />
              exposed and struggling
            </span>
          </div>
          <p className="mt-1.5 min-h-[1.2em] text-[12px]" aria-live="polite">
            {lit === null ? "" : lit === 0 ? "no data here" : BIVAR_WORDS[lit]}
          </p>
        </div>
      )}
      {view !== "bivar" && view !== "priorities" && dim && (
        <Ramp colors={rampFor(dim, pal)} label={`${dim.name}, percentile score`} low={dim.group === "hazard" ? "0 least" : "0"} high={dim.group === "hazard" ? "100 most" : "100"} />
      )}
      {view === "priorities" && <Ramp colors={pal.rampPriority} label="Match with your priorities" low="0 poor" high="100 best" />}
      <ul className="space-y-1 text-[11px] text-muted">
        <li className="flex items-center gap-2">
          <span className="inline-block h-3 w-5 rounded-[2px]" style={{ background: pal.grey }} aria-hidden="true" />
          no data, never shown as zero
        </li>
        {conf && (
          <li className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-5 rounded-[2px]"
              style={{ background: `repeating-linear-gradient(45deg, rgba(${pal.hatch[0]},${pal.hatch[1]},${pal.hatch[2]},0.6) 0 2px, transparent 2px 6px)` }}
              aria-hidden="true"
            />
            fewer than 4 hazard layers, reduced confidence
          </li>
        )}
        {(view === "bivar" || view === "wb") && (
          <li className="flex items-center gap-2">
            <span className="inline-block h-0 w-5 border-t border-dashed" style={{ borderColor: pal.national }} aria-hidden="true" />
            wellbeing from a national figure, not the region
          </li>
        )}
      </ul>
    </div>
  );
}
