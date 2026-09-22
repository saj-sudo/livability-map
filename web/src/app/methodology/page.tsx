import { loadManifest } from "../../lib/manifest";
import type { Manifest, ManifestDimension } from "../../lib/manifest";

// /methodology is generated from manifest.json at build time (SPEC §6.3, §10, invariant 1):
// every number on the map traces back to a source, vintage, license and processing note listed
// here. Nothing on this page is hand-typed data.

export const metadata = { title: "Methodology — livability-map" };

const pct = (share: unknown) => (typeof share === "number" ? `${(100 * share).toFixed(1)}%` : "n/a");
const TAG_ORDER = ["tract", "county", "admin1", "national", "none"];

function CoverageTable({ dims, res }: { dims: ManifestDimension[]; res: string }) {
  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="text-left text-muted">
          <th className="py-1 pr-2">Dimension</th>
          <th className="py-1 pr-2">Kind</th>
          <th className="py-1 pr-2">Coverage</th>
          <th className="py-1 pr-2">Scoring domains</th>
          <th className="py-1">Inhabited hexes by resolution tag (res {res})</th>
        </tr>
      </thead>
      <tbody>
        {dims.map((d) => {
          const cov = (d.coverage && !Array.isArray(d.coverage) ? (d.coverage as Record<string, Record<string, number>>)[res] : undefined) ?? {};
          const total = Object.values(cov).reduce((a, b) => a + b, 0);
          const domains = d.domains?.[res] ?? {};
          return (
            <tr key={d.id} className="border-t border-rule align-top">
              <td className="py-1 pr-2">
                <span className="font-medium">{d.name}</span>
                <div className="text-muted">{d.note}</div>
              </td>
              <td className="py-1 pr-2">
                {d.kind}
                {d.kind === "score" && ` (${d.scale}, higher = ${d.higher_is})`}
              </td>
              <td className="py-1 pr-2">{Array.isArray(d.coverage) ? d.coverage.join(", ") : d.joiners.map((j) => j.domain).filter((v, i, a) => a.indexOf(v) === i).join(", ")}</td>
              <td className="py-1 pr-2">{Object.entries(domains).map(([k, v]) => `${k}: ${v}`).join(", ") || "—"}</td>
              <td className="py-1">
                {total === 0
                  ? "—"
                  : TAG_ORDER.filter((t) => cov[t])
                      .map((t) => `${t} ${((100 * cov[t]) / total).toFixed(1)}%`)
                      .join(" · ")}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function SpotChecks({ m, res }: { m: Manifest; res: string }) {
  const rows = m.spot_checks?.[res] ?? [];
  if (!rows.length) return null;
  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="text-left text-muted">
          <th className="py-1 pr-2">Place</th>
          <th className="py-1 pr-2">Expected</th>
          <th className="py-1 pr-2">Hot days</th>
          <th className="py-1 pr-2">Riverine</th>
          <th className="py-1 pr-2">Coastal</th>
          <th className="py-1 pr-2">Water stress</th>
          <th className="py-1 pr-2">Wellbeing</th>
          <th className="py-1">Class</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={String(r.name)} className="border-t border-rule">
            <td className="py-1 pr-2">
              {String(r.name)}
              {r.note ? <span className="text-muted"> ({String(r.note)})</span> : null}
            </td>
            <td className="py-1 pr-2">{String(r.expect)}</td>
            {r.found ? (
              <>
                <td className="py-1 pr-2">{typeof r.heat_days === "number" ? Math.round(r.heat_days) : "—"}</td>
                <td className="py-1 pr-2">{typeof r.rflood_frac === "number" ? `${(100 * r.rflood_frac).toFixed(1)}%` : "—"}</td>
                <td className="py-1 pr-2">{typeof r.cflood_frac === "number" ? `${(100 * r.cflood_frac).toFixed(1)}%` : "—"}</td>
                <td className="py-1 pr-2">{r.wstress_cat === null || r.wstress_cat === undefined ? "—" : String(r.wstress_cat)}</td>
                <td className="py-1 pr-2">{typeof r.wb_score === "number" ? `${r.wb_score}/100 (${String(r.wb_source)}, ${String(r.wb_res)})` : "—"}</td>
                <td className="py-1">{String(r.bivar ?? "—")}</td>
              </>
            ) : (
              <td className="py-1" colSpan={6}>
                not a land hex in this build
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function Methodology() {
  const m = await loadManifest();
  const resList = m.h3_res.map(String);
  const hasBuild = !!m.built_at;
  const shdi = m.sources.find((s) => s.id === "gdl_shdi");
  return (
    <main className="mx-auto max-w-4xl space-y-8 px-4 py-8 text-sm leading-relaxed">
      <h1 className="text-2xl font-semibold">Methodology</h1>
      {!hasBuild && <p className="rounded border border-amber-300 bg-amber-50 p-3 text-amber-900">This page was built without a pipeline manifest, so the tables below are empty. Run the pipeline and publish to fill them.</p>}
      {m.fixtures && <p className="rounded border border-amber-300 bg-amber-50 p-3 text-amber-900">This build uses the synthetic fixture world, not real data.</p>}

      <section>
        <h2 className="text-lg font-semibold">What the map shows</h2>
        <p>
          Every hexagon carries projected climate hazard exposure for one scenario and horizon (<strong>{m.scenario}</strong>, <strong>{m.horizon}</strong>), present-day wellbeing, and a set of life dimensions you can weight. Hazards are computed per hex from gridded data; everything else is attached at the best available coarser resolution and labelled (<code>admin1</code>, <code>county</code>, <code>tract</code>, <code>national</code>, or <code>none</code>). Hazards are never aggregated up to regions, because within-region variation is exactly what the map exists to show. The map does not recommend where to live.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">How the scores work</h2>
        <ul className="list-disc space-y-1 pl-5">
          {m.processing_notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
          {!m.processing_notes.length && <li>Percentile scores among inhabited hexes; wellbeing min-max within its source; bivariate terciles.</li>}
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Coverage</h2>
        {resList.map((res) => {
          const s = m.coverage_summary?.[res] ?? {};
          return (
            <div key={res} className="mt-2">
              <h3 className="font-medium">H3 resolution {res}</h3>
              <p>
                {String(s.hexes_total ?? "—")} land hexes, {String(s.hexes_inhabited ?? "—")} inhabited. Inhabited hexes with all four hazard layers: {pct(s.share_inhabited_coverage4)}; with none: {pct(s.share_inhabited_coverage0)}. Wellbeing resolution among inhabited hexes: admin1 {String(s.wb_admin1 ?? "—")}, national {String(s.wb_national ?? "—")}, none {String(s.wb_none ?? "—")}.
              </p>
              <CoverageTable dims={[...m.hazards, ...m.dimensions]} res={res} />
            </div>
          );
        })}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Spot checks</h2>
        <p>Four places the pipeline prints on every build so an obviously wrong layer is caught before tiles ship (SPEC §8.5).</p>
        {resList.map((res) => (
          <SpotChecks key={res} m={m} res={res} />
        ))}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Sources</h2>
        <p>All data is open-licensed with attribution. {m.non_commercial && "This project is non-commercial; "}{shdi ? `${shdi.name} is used under terms that allow non-commercial use only.` : ""}</p>
        <table className="mt-2 w-full text-xs">
          <thead>
            <tr className="text-left text-muted">
              <th className="py-1 pr-2">Source</th>
              <th className="py-1 pr-2">Vintage</th>
              <th className="py-1 pr-2">License</th>
              <th className="py-1 pr-2">Processing</th>
              <th className="py-1">Verified</th>
            </tr>
          </thead>
          <tbody>
            {m.sources.map((s) => (
              <tr key={s.id} className="border-t border-rule align-top">
                <td className="py-1 pr-2">
                  {s.url ? (
                    <a className="underline" href={s.url} rel="noreferrer">
                      {s.name}
                    </a>
                  ) : (
                    s.name
                  )}
                  <div className="text-muted">{s.attribution}</div>
                </td>
                <td className="py-1 pr-2">{s.vintage}</td>
                <td className="py-1 pr-2">
                  {s.license}
                  {s.license_note && <div className="text-muted">{s.license_note}</div>}
                </td>
                <td className="py-1 pr-2">{s.processing}</td>
                <td className="py-1">{s.verified}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Known gaps</h2>
        {resList.map((res) => {
          const gaps = m.known_gaps?.[res] ?? {};
          const entries = Object.entries(gaps).filter(([, v]) => Array.isArray((v as { countries_without_data?: unknown }).countries_without_data));
          return (
            <ul key={res} className="list-disc space-y-1 pl-5">
              {entries.map(([id, v]) => {
                const g = v as { countries_without_data: string[]; n_countries_without_data: number; share_inhabited_hexes_missing: number | null };
                return (
                  <li key={id}>
                    <span className="font-medium">{id}</span>: {pct(g.share_inhabited_hexes_missing)} of inhabited hexes have no value; {g.n_countries_without_data} countries have none at all
                    {g.countries_without_data.length ? ` (${g.countries_without_data.join(", ")}${g.n_countries_without_data > g.countries_without_data.length ? ", …" : ""})` : ""}.
                  </li>
                );
              })}
              {!entries.length && <li>No gap statistics in this build.</li>}
            </ul>
          );
        })}
        <p className="mt-2">Small islands and thin coasts whose H3 cell centre falls at sea are not in the grid (Reykjavik&rsquo;s own cell, for example); the spot check falls back to the nearest land hex and says so.</p>
      </section>

      <section className="text-xs text-muted">
        Built {m.built_at ?? "—"}
        {m.published_at ? `, published ${m.published_at}` : ""}. Source code and the full specification are on GitHub (saj-sudo/livability-map).
      </section>
    </main>
  );
}
