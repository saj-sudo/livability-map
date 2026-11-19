"use client";

// The place panel (SPEC §10, §13.50): at most five lead lines, each a finding with its figure
// (lib/lead.ts), then the priorities fit as a band with its working one step in, then one
// disclosure, "All measures and their sources", holding raw values beside ranks with their
// flags, wellbeing with its source and resolution in words, every dimension the manifest lists
// with its resolution or "no data here", and the sources. Every bar is one ink colour and means
// one thing; whether more is better or worse is said in words. Rows are generated from `dims`.

import { Fragment, useEffect, useMemo, useRef } from "react";
import type { SelectedHex } from "./MapView";
import { useTheme } from "./useTheme";
import type { Theme } from "../lib/theme";
import { compositeValue, FIT_BANDS, FIT_WORDS, fitBand, missingNote, priorityBars, type Bar } from "../lib/chart";
import type { ClientManifest } from "../lib/clientManifest";
import { resLabel, shortName, type DimInfo } from "../lib/dims";
import { formatScore } from "../lib/format";
import { describeHex, EXPOSURE_MEANING, MATCH_MEANING, SCORE_MEANING, type LifeRow } from "../lib/inspect";
import { leadLines } from "../lib/lead";
import { paletteFor, SHARE_COLORS } from "../lib/palette";
import { placeHeader } from "../lib/place";
import { presetById } from "../presets";
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
  /** rendered inside the phone bottom sheet: no rail chrome */
  embedded?: boolean;
}

const SOURCE_WORDS: Record<string, string> = { shdi: "Subnational HDI", whr: "World Happiness Report" };

/** A panel section; `scale` names what its numbers are (a match, a rank), right of the title. */
export function Section({ title, scale, children }: { title: string; scale?: string; children: React.ReactNode }) {
  return (
    <section className="mt-3 border-t border-rule pt-2">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h3 className="font-serif text-[14px]">{title}</h3>
        {scale && <span className="text-right text-fine leading-tight text-muted">{scale}</span>}
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
        <li key={b.id} className="grid grid-cols-[1fr_auto] items-center gap-x-2 text-fine">
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

/** The one colour every rank bar uses; direction is said in words beside it (§10). */
const BAR = "var(--ink)";

const direction = (row: LifeRow): string => (row.kind !== "score" ? "" : row.higherIs === "worse" ? "more is worse" : "more is better");

/** One environment or life dimension: value with unit, rank bar, direction in words, coverage chip, resolution. */
function DimRow({ row, theme, track }: { row: LifeRow; theme: Theme; track: string }) {
  return (
    <li key={row.id}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate" title={row.name}>
          {shortName(row.name)}
          {row.chip && <span className="ml-1.5 text-fine text-muted">{row.chip}</span>}
        </span>
        <span className="shrink-0 text-fine text-muted">{resLabel(row.res)}</span>
      </div>
      {row.res !== "none" && (
        <div className="flex items-baseline justify-between gap-2 text-muted">
          <span className="min-w-0">
            {row.value ?? <NoData />}
            {row.score !== null && direction(row) && <span> · {direction(row)}</span>}
          </span>
          {row.score !== null && (
            <span className="shrink-0 whitespace-nowrap tabular-nums text-ink">
              <ScoreBar value={row.score} color={BAR} track={track} /> {formatScore(row.score)}
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
  const preset = presetById(state.preset)?.name ?? null;
  const lines = useMemo(() => leadLines(m, bars, dims, state.weights, picks, hex.props, preset), [m, bars, dims, state.weights, picks, hex.props, preset]);
  const fit = bars.length && m.inhabited ? compositeValue(dims, state.weights, picks, hex.props) : null;
  const band = fit === null ? null : fitBand(fit);
  const header = placeHeader(m, hex.place);
  const missing = missingNote(bars);
  const track = "color-mix(in srgb, var(--rule) 70%, transparent)";
  const measures = m.hazards.length + 1 + m.env.length + m.life.length;
  // keyboard and screen-reader users land on the new place's name (not on every re-render)
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [hex.h3]);

  return (
    <section className={embedded ? "text-small" : "h-full overflow-auto p-4 text-small"} aria-labelledby="place-title">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 id="place-title" ref={heading} tabIndex={-1} className="font-serif text-[22px] leading-tight focus:outline-none focus-visible:outline-2">
            {header.title}
          </h2>
          {header.subtitle && <p className="text-fine">{header.subtitle}</p>}
          <p className="text-fine text-muted">{header.line}.</p>
        </div>
        <button type="button" onClick={onClose} className="-mr-2 -mt-2 grid h-[44px] w-[44px] shrink-0 place-items-center rounded-panel text-muted hover:bg-rule hover:text-ink" aria-label="Close place details">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </button>
      </div>

      <ul className="mt-2" data-testid="lead-lines">
        {lines.map((l) => (
          <li key={l.key} className="border-t border-rule py-2">
            <span className="block text-fine font-semibold text-muted">{l.label}</span>
            <span className="block font-serif text-[16px] leading-snug">{l.text}</span>
            {l.key === "fit" && band && (
              <span className="mt-1.5 block" role="img" aria-label={`${FIT_WORDS[band]}, on a scale of weak, partial, strong`}>
                <span className="grid grid-cols-3 gap-[3px]">
                  {FIT_BANDS.map((b) => (
                    <i key={b} className="block h-2 rounded-[2px]" style={{ background: b === band ? pal.rampPriority[1] : track }} />
                  ))}
                </span>
                <span className="mt-0.5 grid grid-cols-3 text-center text-fine text-muted" aria-hidden="true">
                  {FIT_BANDS.map((b) => (
                    <span key={b} className={b === band ? "font-semibold text-ink" : ""}>
                      {FIT_WORDS[b]}
                    </span>
                  ))}
                </span>
              </span>
            )}
          </li>
        ))}
      </ul>

      {bars.length > 0 && (
        <details className="border-t border-rule">
          <summary className="flex min-h-[44px] cursor-pointer items-center justify-between gap-2">
            <span>How this fit is worked out{fit !== null && <span className="text-muted"> ({Math.round(fit)} of 100)</span>}</span>
            <span aria-hidden="true">›</span>
          </summary>
          <p className="mb-2 text-fine leading-snug text-muted">{MATCH_MEANING}</p>
          <PriorityBars bars={bars} hatchColor={pal.grey} barColor={pal.rampPriority[1]} track={track} />
          {missing && <p className="mt-1.5 text-fine text-muted">{missing}</p>}
          <div className="h-2" />
        </details>
      )}

      <details className="border-t border-rule" data-testid="all-measures">
        <summary className="flex min-h-[44px] cursor-pointer items-center justify-between gap-2 font-semibold">
          <span>
            All {measures} measures and their sources
          </span>
          <span aria-hidden="true">›</span>
        </summary>
        <p className="text-fine leading-snug text-muted">{SCORE_MEANING} Every bar below is that rank; whether more is better or worse is said beside it.</p>

        <Section title={`Climate hazards, ${manifest.horizon}`} scale={`${RANK}; more is worse`}>
          <table className="w-full text-fine">
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
                          <ScoreBar value={h.score} color={BAR} track={track} /> <span className="ml-1">{formatScore(h.score)}</span>
                        </>
                      ) : (
                        <span className="text-muted">no data</span>
                      )}
                    </td>
                  </tr>
                  {h.note && (
                    <tr>
                      <td colSpan={3} className="pb-[3px] text-fine leading-snug text-muted">
                        {h.note}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-fine text-muted">
            {m.coverage}
            {m.exposure !== null ? `; combined exposure ${formatScore(m.exposure)}, ${EXPOSURE_MEANING}` : "; combined exposure not computed"}.
          </p>
        </Section>

        <Section title="Wellbeing" scale="score 0-100 within its source">
          <p className="text-fine">
            {m.wellbeing.value ?? <NoData />}
            {m.wellbeing.score !== null && (
              <>
                {" "}
                <ScoreBar value={m.wellbeing.score} color={BAR} track={track} /> {formatScore(m.wellbeing.score)}
              </>
            )}
          </p>
          {m.wellbeing.source !== "none" && (
            <p className="text-fine text-muted">
              {SOURCE_WORDS[m.wellbeing.source] ?? m.wellbeing.source}, {resLabel(m.wellbeing.res)}
            </p>
          )}
          <p className="mt-1 text-fine">Beside exposure: {m.wellbeing.res === "national" && m.bivarClass ? `${m.bivar} (wellbeing is the national figure, so the map shows exposure only here)` : m.bivar}.</p>
        </Section>

        {m.env.length > 0 && (
          <Section title="Environment today" scale={RANK}>
            <p className="mb-1 text-fine text-muted">Observed, not projected; not part of the exposure score.</p>
            <ul className="space-y-1.5 text-fine">
              {m.env.map((row) => (
                <DimRow key={row.id} row={row} theme={theme} track={track} />
              ))}
            </ul>
          </Section>
        )}

        <Section title="Life dimensions" scale={RANK}>
          <ul className="space-y-1.5 text-fine">
            {m.life.map((row) => (
              <DimRow key={row.id} row={row} theme={theme} track={track} />
            ))}
          </ul>
        </Section>

        <Section title={`Sources (${m.sources.length})`}>
          <ul className="space-y-1 text-fine">
            {m.sources.map((s) => (
              <li key={s.id}>
                <span className="font-medium">{s.name}</span>, {s.vintage}. {s.license}
                {s.license_note && ` (${s.license_note})`}. {s.attribution}
                {s.processing && <span className="text-muted"> {s.processing}</span>}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-fine text-muted">Built {manifest.built_at?.slice(0, 10) ?? "—"}; full details under Methodology.</p>
        </Section>
        <div className="h-2" />
      </details>

      {onCompare && (
        <button type="button" onClick={onCompare} disabled={picking} className="mt-2 flex min-h-[44px] w-full items-center justify-between rounded-panel border border-rule px-3 text-small hover:border-muted disabled:text-muted">
          {picking ? "Pick a second place on the map, or search for one" : "Compare with another place"}
          <span aria-hidden="true">›</span>
        </button>
      )}
    </section>
  );
}
