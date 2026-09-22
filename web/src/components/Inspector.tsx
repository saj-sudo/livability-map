"use client";

// Click-a-hex inspector (SPEC §10): a plain-language summary, raw values beside scores with
// their flags, wellbeing with its source and resolution in words, the person's weighted
// priorities as bars, every dimension the manifest lists with its resolution or "no data
// here", and a Sources disclosure. Rows are generated from `dims`, so new dimensions appear.

import { useMemo } from "react";
import type { SelectedHex } from "./MapView";
import { useTheme } from "./useTheme";
import type { Theme } from "../lib/theme";
import { priorityBars, type Bar } from "../lib/chart";
import type { ClientManifest } from "../lib/clientManifest";
import { shortName, type DimInfo } from "../lib/dims";
import { formatScore } from "../lib/format";
import { describeHex, type LifeRow } from "../lib/inspect";
import { paletteFor, SHARE_COLORS, type Palette } from "../lib/palette";
import { summarize } from "../lib/summary";
import type { AppState } from "../lib/url";

interface Props {
  hex: SelectedHex;
  manifest: ClientManifest;
  dims: DimInfo[];
  state: AppState;
  onClose: () => void;
  onCompare?: () => void;
  /** rendered inside the phone bottom sheet: no floating chrome */
  embedded?: boolean;
}

const RES_WORDS: Record<string, string> = { hex: "this hex", basin: "sub-basin", tract: "tract level", county: "county level", admin1: "regional figure", national: "national figure", none: "no data here" };
const SOURCE_WORDS: Record<string, string> = { shdi: "Subnational HDI", whr: "World Happiness Report" };

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-3 border-t border-rule pt-2">
      <h3 className="mb-1 font-serif text-[14px]">{title}</h3>
      {children}
    </section>
  );
}

const NoData = () => <span className="text-muted">no data here</span>;

/** A thin score bar: 0-100 in one hue, value labelled in text (dataviz: thin marks, text in ink). */
export function ScoreBar({ value, color, track }: { value: number | null; color: string; track: string }) {
  return (
    <span className="inline-block h-[5px] w-14 overflow-hidden rounded-[2px] align-middle" style={{ background: track }} aria-hidden="true">
      {value !== null && <span className="block h-full rounded-[2px]" style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: color }} />}
    </span>
  );
}

export function PriorityBars({ bars, hatchColor, barColor, track }: { bars: Bar[]; hatchColor: string; barColor: string; track: string }) {
  return (
    <ul className="space-y-1.5">
      {bars.map((b) => (
        <li key={b.id} className="grid grid-cols-[1fr_auto] items-center gap-x-2 text-[12px]">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate" title={b.name}>
              {shortName(b.name)} <span className="text-muted">×{b.weight}</span>
            </span>
            <span className="shrink-0 tabular-nums">{b.match === null ? <NoData /> : formatScore(b.match)}</span>
          </div>
          <span className="block h-2 w-24 overflow-hidden rounded-[2px]" style={{ background: b.match === null ? `repeating-linear-gradient(45deg, ${hatchColor} 0 2px, transparent 2px 6px)` : track }} role="img" aria-label={`${b.name}: ${b.match === null ? "no data here" : formatScore(b.match)}`}>
            {b.match !== null && <span className="block h-full rounded-[2px]" style={{ width: `${Math.max(2, b.match)}%`, background: barColor }} />}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** One environment or life dimension: value with unit, score bar, coverage chip, resolution. */
function DimRow({ row, theme, pal, track }: { row: LifeRow; theme: Theme; pal: Palette; track: string }) {
  return (
    <li key={row.id}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate" title={row.name}>
          {shortName(row.name)}
          {row.chip && <span className="ml-1.5 text-[11px] text-muted">{row.chip}</span>}
        </span>
        <span className="shrink-0 text-[11px] text-muted">{RES_WORDS[row.res] ?? row.res}</span>
      </div>
      {row.res !== "none" && (
        <div className="flex items-baseline justify-between gap-2 text-muted">
          <span className="min-w-0">{row.value ?? <NoData />}</span>
          {row.score !== null && (
            <span className="shrink-0 whitespace-nowrap tabular-nums text-ink">
              <ScoreBar value={row.score} color={pal.rampGood[1]} track={track} /> {formatScore(row.score)}
            </span>
          )}
        </div>
      )}
      {row.shares && row.res !== "none" && (
        <div className="mt-1 flex h-2 w-full gap-px overflow-hidden rounded-[2px]" role="img" aria-label={row.shares.map((s) => `${s.label} ${s.pct}%`).join(", ")}>
          {row.shares.map((s, i) => (
            <span key={s.key} title={`${s.label} ${s.pct}%`} style={{ width: `${s.pct}%`, background: SHARE_COLORS[theme][i] }} />
          ))}
        </div>
      )}
    </li>
  );
}

export default function Inspector({ hex, manifest, dims, state, onClose, onCompare, embedded }: Props) {
  const [theme] = useTheme();
  const pal = paletteFor(theme);
  const picks = useMemo(() => ({ pol: state.pol, race: state.race }), [state.pol, state.race]);
  const m = useMemo(() => describeHex(hex.props, hex.sourceLayer, dims, manifest), [hex, dims, manifest]);
  const bars = useMemo(() => priorityBars(hex.props, dims, state.weights, picks), [hex, dims, state.weights, picks]);
  const summary = summarize(m, bars, dims, state.weights, picks, hex.props);
  const track = "color-mix(in srgb, var(--rule) 70%, transparent)";

  return (
    <section className={embedded ? "text-[13px]" : "absolute bottom-3 right-3 z-10 max-h-[calc(100%-1.5rem)] w-[23rem] max-w-[calc(100%-1.5rem)] overflow-auto rounded-panel border border-rule bg-panel p-3 text-[13px] shadow-[0_1px_2px_rgba(0,0,0,.06),0_8px_24px_-12px_rgba(0,0,0,.25)] backdrop-blur-sm"} aria-label="Hex details">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="font-serif text-[19px] leading-tight">{m.title}</h2>
          <p className="text-[12px] text-muted">
            {m.subtitle ? `${m.subtitle}. ` : ""}
            {m.population} in a {m.resolution.replace("H3 ", "").replace(" (~", ", about ").replace(")", "")}.
          </p>
        </div>
        <button type="button" onClick={onClose} className="-mr-1 -mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-panel text-muted hover:bg-rule hover:text-ink" aria-label="Close">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </button>
      </div>

      <p className="mt-2 font-serif text-[14px] leading-snug">{summary}</p>

      {bars.length > 0 && (
        <Section title="Your priorities">
          <PriorityBars bars={bars} hatchColor={pal.grey} barColor={pal.rampPriority[1]} track={track} />
        </Section>
      )}

      <Section title={`Climate hazards, ${manifest.horizon}`}>
        <table className="w-full text-[12px]">
          <tbody>
            {m.hazards.map((h) => (
              <tr key={h.id} className="align-baseline">
                <td className="py-[3px] pr-2" title={h.name}>
                  {shortName(h.name)}
                </td>
                <td className="py-[3px] pr-2 text-muted">{h.raw ?? <NoData />}</td>
                <td className="whitespace-nowrap py-[3px] text-right tabular-nums">
                  {h.ok && h.score !== null ? (
                    <>
                      <ScoreBar value={h.score} color={pal.rampHazard[1]} track={track} /> <span className="ml-1">{formatScore(h.score)}</span>
                    </>
                  ) : (
                    <span className="text-muted">no data</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-[12px] text-muted">
          {m.coverage}
          {m.exposure !== null ? `; combined exposure ${formatScore(m.exposure)}` : "; exposure not computed"}
        </p>
      </Section>

      <Section title="Wellbeing">
        <p className="text-[12px]">
          {m.wellbeing.value ?? <NoData />}
          {m.wellbeing.score !== null && (
            <>
              {" "}
              <ScoreBar value={m.wellbeing.score} color={pal.rampWellbeing[1]} track={track} /> {formatScore(m.wellbeing.score)}
            </>
          )}
        </p>
        {m.wellbeing.source !== "none" && (
          <p className="text-[12px] text-muted">
            {SOURCE_WORDS[m.wellbeing.source] ?? m.wellbeing.source}, {RES_WORDS[m.wellbeing.res] ?? m.wellbeing.res}
          </p>
        )}
        <p className="mt-1 text-[12px]">Combined: {m.bivar}.</p>
      </Section>

      {m.env.length > 0 && (
        <Section title="Environment today">
          <p className="mb-1 text-[11px] text-muted">Observed, not projected; not part of the exposure score.</p>
          <ul className="space-y-1.5 text-[12px]">
            {m.env.map((row) => (
              <DimRow key={row.id} row={row} theme={theme} pal={pal} track={track} />
            ))}
          </ul>
        </Section>
      )}

      <Section title="Life dimensions">
        <ul className="space-y-1.5 text-[12px]">
          {m.life.map((row) => (
            <DimRow key={row.id} row={row} theme={theme} pal={pal} track={track} />
          ))}
        </ul>
      </Section>

      <details className="mt-3 border-t border-rule pt-2 text-[12px]">
        <summary className="cursor-pointer font-serif text-[14px]">Sources ({m.sources.length})</summary>
        <ul className="mt-1 space-y-1">
          {m.sources.map((s) => (
            <li key={s.id}>
              <span className="font-medium">{s.name}</span>, {s.vintage}. {s.license}
              {s.license_note && ` (${s.license_note})`}. {s.attribution}
              {s.processing && <span className="text-muted"> {s.processing}</span>}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-muted">Built {manifest.built_at?.slice(0, 10) ?? "—"}; full details under Methodology.</p>
      </details>

      {onCompare && (
        <button type="button" onClick={onCompare} className="mt-3 w-full rounded-panel border border-rule bg-panel-solid py-1.5 text-[13px] hover:border-muted">
          Compare with another place
        </button>
      )}
    </section>
  );
}
