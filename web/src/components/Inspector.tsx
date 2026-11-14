"use client";

// Click-a-hex inspector (SPEC §10): a plain-language summary, raw values beside scores with
// their flags, wellbeing with its source and resolution in words, the person's weighted
// priorities as bars, every dimension the manifest lists with its resolution or "no data
// here", and a Sources disclosure. Rows are generated from `dims`, so new dimensions appear.

import { Fragment, useEffect, useMemo, useRef } from "react";
import type { SelectedHex } from "./MapView";
import { useTheme } from "./useTheme";
import type { Theme } from "../lib/theme";
import { missingNote, priorityBars, type Bar } from "../lib/chart";
import type { ClientManifest } from "../lib/clientManifest";
import { resLabel, shortName, type DimInfo } from "../lib/dims";
import { formatScore } from "../lib/format";
import { describeHex, EXPOSURE_MEANING, scoreNoteFor, type LifeRow } from "../lib/inspect";
import { paletteFor, scoreBarColor, SHARE_COLORS, type Palette } from "../lib/palette";
import { placeHeader } from "../lib/place";
import { summarize } from "../lib/summary";
import type { AppState } from "../lib/url";

interface Props {
  hex: SelectedHex;
  manifest: ClientManifest;
  dims: DimInfo[];
  state: AppState;
  onClose: () => void;
  onCompare?: () => void;
  /** a second place is being picked for a comparison */
  picking?: boolean;
  /** rendered inside the phone bottom sheet: no floating chrome */
  embedded?: boolean;
}

const SOURCE_WORDS: Record<string, string> = { shdi: "Subnational HDI", whr: "World Happiness Report" };

/** A panel section; `scale` names what its numbers are (a match, a rank), right of the title. */
export function Section({ title, scale, children }: { title: string; scale?: string; children: React.ReactNode }) {
  return (
    <section className="mt-3 border-t border-rule pt-2">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h3 className="font-serif text-[14px]">{title}</h3>
        {scale && <span className="text-right text-[11px] leading-tight text-muted">{scale}</span>}
      </div>
      {children}
    </section>
  );
}

const RANK = "rank among inhabited places, 0-100";

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
        <span className="shrink-0 text-[11px] text-muted">{resLabel(row.res)}</span>
      </div>
      {row.res !== "none" && (
        <div className="flex items-baseline justify-between gap-2 text-muted">
          <span className="min-w-0">{row.value ?? <NoData />}</span>
          {row.score !== null && (
            <span className="shrink-0 whitespace-nowrap tabular-nums text-ink">
              <ScoreBar value={row.score} color={scoreBarColor(pal, row.higherIs)} track={track} /> {formatScore(row.score)}
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

export default function Inspector({ hex, manifest, dims, state, onClose, onCompare, picking, embedded }: Props) {
  const [theme] = useTheme();
  const pal = paletteFor(theme);
  const picks = useMemo(() => ({ pol: state.pol }), [state.pol]);
  const m = useMemo(() => describeHex(hex.props, hex.sourceLayer, dims, manifest), [hex, dims, manifest]);
  const bars = useMemo(() => priorityBars(hex.props, dims, state.weights, picks), [hex, dims, state.weights, picks]);
  const summary = summarize(m, bars, dims, state.weights, picks, hex.props);
  const header = placeHeader(m, hex.place);
  const missing = missingNote(bars);
  const track = "color-mix(in srgb, var(--rule) 70%, transparent)";
  // keyboard and screen-reader users land on the new place's name (not on every re-render)
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [hex.h3]);

  return (
    <section className={embedded ? "text-[13px]" : "absolute bottom-3 right-3 z-10 max-h-[calc(100%-1.5rem)] w-[23rem] max-w-[calc(100%-1.5rem)] overflow-auto rounded-panel border border-rule bg-panel p-3 text-[13px] shadow-[0_1px_2px_rgba(0,0,0,.06),0_8px_24px_-12px_rgba(0,0,0,.25)] backdrop-blur-sm"} aria-labelledby="place-title">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 id="place-title" ref={heading} tabIndex={-1} className="font-serif text-[19px] leading-tight focus:outline-none focus-visible:outline-2">
            {header.title}
          </h2>
          {header.subtitle && <p className="text-[12px]">{header.subtitle}</p>}
          <p className="text-[12px] text-muted">
            {header.line}.
          </p>
        </div>
        <button type="button" onClick={onClose} className="-mr-1 -mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-panel text-muted hover:bg-rule hover:text-ink" aria-label="Close place details">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </button>
      </div>

      <p className="mt-2 font-serif text-[14px] leading-snug">{summary}</p>
      <p className="mt-1.5 text-[12px] leading-snug text-muted">
        {scoreNoteFor(bars.length > 0)}
      </p>

      {bars.length > 0 && (
        <Section title="Your priorities" scale="match with your priorities, 0-100">
          <PriorityBars bars={bars} hatchColor={pal.grey} barColor={pal.rampPriority[1]} track={track} />
          {missing && <p className="mt-1.5 text-[12px] text-muted">{missing}</p>}
        </Section>
      )}

      <Section title={`Climate hazards, ${manifest.horizon}`} scale={RANK}>
        <table className="w-full text-[12px]">
          <thead className="sr-only">
            <tr>
              <th scope="col">Hazard</th>
              <th scope="col">Projected value</th>
              <th scope="col">Rank among inhabited places</th>
            </tr>
          </thead>
          <tbody>
            {m.hazards.map((h) => (
              <Fragment key={h.id}>
              <tr className="align-baseline">
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
              {h.note && (
                <tr>
                  <td colSpan={3} className="pb-[3px] text-[11px] leading-snug text-muted">
                    {h.note}
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-[12px] text-muted">
          {m.coverage}
          {m.exposure !== null ? `; combined exposure ${formatScore(m.exposure)}, ${EXPOSURE_MEANING}` : "; combined exposure not computed"}.
        </p>
      </Section>

      <Section title="Wellbeing" scale="score 0-100 within its source">
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
            {SOURCE_WORDS[m.wellbeing.source] ?? m.wellbeing.source}, {resLabel(m.wellbeing.res)}
          </p>
        )}
        <p className="mt-1 text-[12px]">Combined: {m.bivar}.</p>
      </Section>

      {m.env.length > 0 && (
        <Section title="Environment today" scale={RANK}>
          <p className="mb-1 text-[11px] text-muted">Observed, not projected; not part of the exposure score.</p>
          <ul className="space-y-1.5 text-[12px]">
            {m.env.map((row) => (
              <DimRow key={row.id} row={row} theme={theme} pal={pal} track={track} />
            ))}
          </ul>
        </Section>
      )}

      <Section title="Life dimensions" scale={RANK}>
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
        <button type="button" onClick={onCompare} disabled={picking} className="mt-3 w-full rounded-panel border border-rule bg-panel-solid py-1.5 text-[13px] hover:border-muted disabled:text-muted">
          {picking ? "Pick a second place on the map, or search for one" : "Compare with another place"}
        </button>
      )}
    </section>
  );
}
