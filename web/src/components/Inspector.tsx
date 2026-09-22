"use client";

// Click-a-hex inspector (SPEC §10): raw values beside scores with their flags, wellbeing with
// source and resolution badges, coverage, the bivariate class in words, each life dimension
// with its resolution badge or "no data here", and a Sources disclosure from the manifest.

import type { SelectedHex } from "./MapView";
import type { ClientManifest } from "../lib/clientManifest";
import type { DimInfo } from "../lib/dims";
import { describeHex } from "../lib/inspect";

interface Props {
  hex: SelectedHex;
  manifest: ClientManifest;
  dims: DimInfo[];
  onClose: () => void;
}

function Badge({ children, tone = "grey" }: { children: React.ReactNode; tone?: "grey" | "warn" }) {
  const cls = tone === "warn" ? "bg-amber-100 text-amber-900" : "bg-gray-100 text-gray-700";
  return <span className={`ml-1 rounded px-1 py-0.5 text-[10px] uppercase tracking-wide ${cls}`}>{children}</span>;
}

const NoData = () => <span className="text-[var(--muted)]">no data here</span>;

export default function Inspector({ hex, manifest, dims, onClose }: Props) {
  const m = describeHex(hex.props, hex.sourceLayer, dims, manifest);
  return (
    <section className="absolute bottom-3 right-3 z-10 max-h-[calc(100%-1.5rem)] w-[22rem] max-w-[calc(100%-1.5rem)] overflow-auto rounded-lg border border-[var(--border)] bg-[var(--panel)] p-3 text-sm shadow-md" aria-label="Hex details">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold leading-tight">{m.title}</h2>
          <div className="text-xs text-[var(--muted)]">
            {m.subtitle && <span>{m.subtitle} · </span>}
            {m.population} · {m.resolution}
            {!m.inhabited && <Badge tone="warn">uninhabited</Badge>}
          </div>
        </div>
        <button type="button" onClick={onClose} className="rounded px-2 text-lg leading-none text-[var(--muted)] hover:bg-gray-100" aria-label="Close">
          ×
        </button>
      </div>

      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Climate hazards, {manifest.horizon}</h3>
      <table className="mt-1 w-full text-xs">
        <tbody>
          {m.hazards.map((h) => (
            <tr key={h.id} className="border-t border-[var(--border)]">
              <td className="py-1 pr-2">{h.name}</td>
              <td className="py-1 pr-2">{h.raw ?? <NoData />}</td>
              <td className="py-1 text-right tabular-nums">{h.ok && h.score !== null ? `${h.score}/100` : <Badge tone="warn">no data</Badge>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-xs">
        {m.coverage}
        {m.exposure !== null ? ` · exposure ${m.exposure}/100` : " · exposure not computed"}
      </p>

      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Wellbeing</h3>
      <p className="text-xs">
        {m.wellbeing.value ?? <NoData />}
        {m.wellbeing.score !== null && ` · ${m.wellbeing.score}/100`}
        {m.wellbeing.source !== "none" && <Badge>{m.wellbeing.source}</Badge>}
        <Badge tone={m.wellbeing.res === "national" ? "warn" : "grey"}>{m.wellbeing.res}</Badge>
      </p>
      <p className="mt-1 text-xs">Combined: {m.bivar}.</p>

      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Life dimensions</h3>
      <ul className="mt-1 space-y-1 text-xs">
        {m.life.map((row) => (
          <li key={row.id} className="border-t border-[var(--border)] pt-1">
            <div className="flex items-center justify-between gap-2">
              <span>
                {row.name}
                {row.chip && <Badge>{row.chip}</Badge>}
              </span>
              <Badge tone={row.res === "none" ? "warn" : "grey"}>{row.res}</Badge>
            </div>
            <div className="text-[var(--muted)]">
              {row.value ?? <NoData />}
              {row.score !== null && ` · ${row.score}/100`}
            </div>
            {row.shares && row.res !== "none" && (
              <div className="mt-1 flex h-2 w-full overflow-hidden rounded" role="img" aria-label={row.shares.map((s) => `${s.label} ${s.pct}%`).join(", ")}>
                {row.shares.map((s, i) => (
                  <span key={s.key} title={`${s.label} ${s.pct}%`} style={{ width: `${s.pct}%`, background: ["#8c6bb1", "#41ab5d", "#fd8d3c", "#4292c6", "#bdbdbd"][i] }} />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>

      <details className="mt-3 text-xs">
        <summary className="cursor-pointer font-semibold">Sources ({m.sources.length})</summary>
        <ul className="mt-1 space-y-1">
          {m.sources.map((s) => (
            <li key={s.id}>
              <span className="font-medium">{s.name}</span> — {s.vintage}. {s.license}
              {s.license_note && ` (${s.license_note})`}. {s.attribution}
              {s.processing && <span className="text-[var(--muted)]"> · {s.processing}</span>}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-[var(--muted)]">Built {manifest.built_at ?? "—"}; full details under Methodology.</p>
      </details>
    </section>
  );
}
