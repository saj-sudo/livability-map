// Legend (SPEC §9.3, §10): 3x3 bivariate grid with axis labels, sequential ramps for single
// layers and the priorities composite, the confidence hatch key and the national-fallback key.

import type { DimInfo } from "../lib/dims";
import { rampFor } from "../lib/expressions";
import { BIVAR, GREY, RAMP_PRIORITY } from "../lib/palette";
import type { ViewId } from "../lib/url";

interface Props {
  view: ViewId;
  dims: DimInfo[];
  conf: boolean;
}

function Ramp({ colors, low, high }: { colors: string[]; low: string; high: string }) {
  return (
    <div>
      <div className="h-3 w-full rounded" style={{ background: `linear-gradient(90deg, ${colors[0]}, ${colors[1]}, ${colors[2]})` }} aria-hidden="true" />
      <div className="flex justify-between text-[10px] text-[var(--muted)]">
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </div>
  );
}

export default function Legend({ view, dims, conf }: Props) {
  const dim = dims.find((d) => d.id === view);
  return (
    <div className="space-y-2 border-t border-[var(--border)] pt-2 text-xs">
      {view === "bivar" && (
        <div className="flex items-end gap-2">
          <div className="flex flex-col items-center gap-1" aria-hidden="true">
            <span className="text-[10px] text-[var(--muted)]" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
              higher wellbeing ↑
            </span>
          </div>
          <div>
            <div className="grid grid-cols-3 gap-px" role="img" aria-label="Bivariate legend: rows are wellbeing terciles from low at the bottom to high at the top; columns are climate exposure terciles from low on the left to high on the right">
              {[7, 8, 9, 4, 5, 6, 1, 2, 3].map((k) => (
                <div key={k} className="h-5 w-5" style={{ background: BIVAR[k] }} title={`class ${k}`} />
              ))}
            </div>
            <div className="mt-1 text-[10px] text-[var(--muted)]">more climate exposure →</div>
          </div>
        </div>
      )}
      {view !== "bivar" && view !== "priorities" && dim && (
        <div>
          <div className="mb-1">{dim.name}: percentile score</div>
          <Ramp colors={rampFor(dim)} low={dim.group === "hazard" ? "0 (least hazard)" : "0"} high={dim.group === "hazard" ? "100 (most hazard)" : "100"} />
        </div>
      )}
      {view === "priorities" && (
        <div>
          <div className="mb-1">Match with your priorities</div>
          <Ramp colors={RAMP_PRIORITY} low="0 (poor match)" high="100 (best match)" />
        </div>
      )}
      <ul className="space-y-1">
        <li className="flex items-center gap-2">
          <span className="inline-block h-3 w-5 rounded-sm" style={{ background: GREY }} aria-hidden="true" />
          no data (never shown as zero)
        </li>
        {conf && (
          <li className="flex items-center gap-2">
            <span className="inline-block h-3 w-5 rounded-sm" style={{ background: "repeating-linear-gradient(45deg, rgba(40,40,40,.6) 0 2px, transparent 2px 6px)" }} aria-hidden="true" />
            fewer than 4 hazard layers (reduced confidence)
          </li>
        )}
        {(view === "bivar" || view === "wb") && (
          <li className="flex items-center gap-2">
            <span className="inline-block h-0 w-5 border-t-2 border-dashed border-gray-600" aria-hidden="true" />
            wellbeing from a national figure, not the region
          </li>
        )}
      </ul>
    </div>
  );
}
