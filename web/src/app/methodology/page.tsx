import { domainLabel, resLabel } from "../../lib/dims";
import { formatHazardRaw } from "../../lib/format";
import { EXPOSURE_MEANING, HEAT_CAVEAT, hexAreaKm2, SCORE_MEANING } from "../../lib/inspect";
import { loadManifest } from "../../lib/manifest";
import type { Manifest, ManifestDimension } from "../../lib/manifest";
import { kindWords, verifiedWords } from "../../lib/methodology";
import { BIVAR_WORDS } from "../../lib/palette";

// /methodology is generated from manifest.json at build time (SPEC §6.3, §10, invariant 1):
// every number on the map traces back to a source, vintage, license and processing note listed
// here. Nothing on this page is hand-typed data. Codes from the manifest (resolution tags,
// scoring domains, kinds, verification status) are shown in words (lib/dims.ts, lib/methodology.ts).

export const metadata = { title: "Methodology — livability-map" };

const pct = (share: unknown) => (typeof share === "number" ? `${(100 * share).toFixed(1)}%` : "n/a");
const TAG_ORDER = ["hex", "grid", "basin", "tract", "area", "county", "admin1", "national", "none"];
const REPO = "https://github.com/saj-sudo/livability-map";

/** "hexagons of about 1,770 km²" for a resolution number. */
const scaleName = (res: string): string => {
  const a = hexAreaKm2(Number(res));
  return a ? `Hexagons of about ${a} km²` : `Map scale ${res}`;
};

/** Theme-aware notice (theme tokens, so it works in dark mode). */
function Notice({ children }: { children: React.ReactNode }) {
  return <p className="rounded-panel border border-l-4 border-rule border-l-accent bg-panel-solid p-3">{children}</p>;
}

/** Wide tables scroll sideways in their own box on a phone instead of widening the page. */
function Wide({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto">{children}</div>;
}

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="font-serif text-xl">{children}</h2>;
}

function CoverageTable({ dims, res }: { dims: ManifestDimension[]; res: string }) {
  return (
    <Wide>
      <table className="mt-2 w-full min-w-[44rem] text-xs">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 pr-2">Layer</th>
            <th className="py-1 pr-2">What the number is</th>
            <th className="py-1 pr-2">Coverage</th>
            <th className="py-1 pr-2">Places ranked against each other</th>
            <th className="py-1">Where the value comes from (share of inhabited places)</th>
          </tr>
        </thead>
        <tbody>
          {dims.map((d) => {
            const cov = (d.coverage && !Array.isArray(d.coverage) ? (d.coverage as Record<string, Record<string, number>>)[res] : undefined) ?? {};
            const total = Object.values(cov).reduce((a, b) => a + b, 0);
            const domains = d.domains?.[res] ?? {};
            const coverage = Array.isArray(d.coverage) ? d.coverage.map(String) : (d.joiners ?? []).map((j) => j.domain ?? "").filter((v, i, a) => v && a.indexOf(v) === i);
            return (
              <tr key={d.id} className="border-t border-rule align-top">
                <td className="py-1 pr-2">
                  <span className="font-medium">{d.name}</span>
                  <div className="text-muted">{d.note}</div>
                </td>
                <td className="py-1 pr-2">{kindWords(d)}</td>
                <td className="py-1 pr-2">{[...new Set(coverage.map(domainLabel))].join(", ")}</td>
                <td className="py-1 pr-2">{Object.entries(domains).map(([k, v]) => `${domainLabel(k)}: ${v.toLocaleString("en-US")}`).join(", ") || "n/a"}</td>
                <td className="py-1">
                  {total === 0
                    ? "n/a"
                    : TAG_ORDER.filter((t) => cov[t])
                        .map((t) => `${resLabel(t)} ${((100 * cov[t]) / total).toFixed(1)}%`)
                        .join(" · ")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Wide>
  );
}

function SpotChecks({ m, res }: { m: Manifest; res: string }) {
  const rows = m.spot_checks?.[res] ?? [];
  if (!rows.length) return null;
  return (
    <Wide>
      <table className="mt-2 w-full min-w-[44rem] text-xs">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 pr-2">Place</th>
            <th className="py-1 pr-2">Expected</th>
            <th className="py-1 pr-2">Hot days</th>
            <th className="py-1 pr-2">Riverine flood</th>
            <th className="py-1 pr-2">Coastal flood</th>
            <th className="py-1 pr-2">Water stress</th>
            <th className="py-1 pr-2">Wellbeing</th>
            <th className="py-1">Colour on the map</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.name)} className="border-t border-rule align-top">
              <td className="py-1 pr-2">
                {String(r.name)}
                {r.note ? <span className="text-muted"> ({String(r.note)})</span> : null}
              </td>
              <td className="py-1 pr-2">{String(r.expect)}</td>
              {r.found ? (
                <>
                  <td className="py-1 pr-2">{typeof r.heat_days === "number" ? Math.round(r.heat_days) : "no data"}</td>
                  <td className="py-1 pr-2">{typeof r.rflood_frac === "number" ? `${(100 * r.rflood_frac).toFixed(1)}%` : "no data"}</td>
                  <td className="py-1 pr-2">{typeof r.cflood_frac === "number" ? `${(100 * r.cflood_frac).toFixed(1)}%` : "no data"}</td>
                  <td className="py-1 pr-2">{typeof r.wstress_cat === "number" ? formatHazardRaw("wstress", r.wstress_cat) : "no data"}</td>
                  <td className="py-1 pr-2">{typeof r.wb_score === "number" ? `${r.wb_score}/100 (${String(r.wb_source)}, ${resLabel(String(r.wb_res))})` : "no data"}</td>
                  <td className="py-1">{typeof r.bivar === "number" ? (BIVAR_WORDS[r.bivar] ?? String(r.bivar)) : "no data"}</td>
                </>
              ) : (
                <td className="py-1" colSpan={6}>
                  not on land in this build
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </Wide>
  );
}

export default async function Methodology() {
  const m = await loadManifest();
  const resList = m.h3_res.map(String);
  const hasBuild = !!m.built_at;
  const shdi = m.sources.find((s) => s.id === "gdl_shdi");
  const names = new Map([...m.hazards, ...m.dimensions].map((d) => [d.id, d.name]));
  return (
    <main className="mx-auto max-w-4xl space-y-8 px-4 py-8 text-sm leading-relaxed">
      <h1 className="font-serif text-3xl">Methodology</h1>
      {!hasBuild && <Notice>This page was built without a pipeline manifest, so the tables below are empty. Run the pipeline and publish to fill them.</Notice>}
      {m.fixtures && <Notice>This build uses the synthetic fixture world, not real data.</Notice>}

      <section className="space-y-2">
        <H2>How to read the map</H2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>Colours.</strong> In the default view each hexagon is coloured by two things at once: projected climate exposure in {m.horizon} (redder means more) and present-day wellbeing (bluer means higher). The colour key sits in the Layers panel, or in the Layers tab on a phone.
          </li>
          <li>
            <strong>Scores are ranks, not risk.</strong> A score of 80 means the place ranks above 80% of inhabited places on that layer. It does not mean an 80% chance of anything, and it is not twice as bad as 40.
          </li>
          <li>
            <strong>Grey or hatched means missing data.</strong> Grey is no data at all, never zero risk. Hatching marks places where some of the four hazard layers are missing, so the picture is less complete.
          </li>
          <li>
            <strong>Your priorities are yours.</strong> In My priorities the colour is a match from 0 to 100 with the weights you chose, worked out in your browser.
          </li>
          <li>
            <strong>It does not recommend where to live.</strong> The map shows evidence, its sources and its gaps; the decision stays with you.
          </li>
        </ul>
      </section>

      <section>
        <H2>What the map shows</H2>
        <p>
          Every hexagon carries projected climate hazard exposure for one scenario and horizon (<strong>{m.scenario}</strong>, <strong>{m.horizon}</strong>), present-day wellbeing, and a set of life dimensions you can weight. Hazards are computed for each hexagon from gridded data; everything else is attached at the best available coarser level and labelled as such (a census tract, a county figure, a regional figure, a national figure, or no data here). Hazards are never averaged up to regions, because the differences within a region are exactly what the map exists to show. The map does not recommend where to live.
        </p>
      </section>

      <section>
        <H2>How the scores work</H2>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>{SCORE_MEANING}</strong> A score of 80 does not mean 80% likely, or twice as bad as 40.
          </li>
          <li>Combined exposure is {EXPOSURE_MEANING}.</li>
          {m.processing_notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
          {!m.processing_notes.length && <li>Hazards and life dimensions are ranked among inhabited places; wellbeing is scaled 0-100 within its source; the default colours split each side into thirds.</li>}
        </ul>
      </section>

      <section>
        <H2>Coverage</H2>
        {resList.map((res) => {
          const s = m.coverage_summary?.[res] ?? {};
          return (
            <div key={res} className="mt-2">
              <h3 className="font-medium">{scaleName(res)}</h3>
              <p>
                {String(s.hexes_total ?? "n/a")} hexagons on land, {String(s.hexes_inhabited ?? "n/a")} of them inhabited. Inhabited places with all four hazard layers: {pct(s.share_inhabited_coverage4)}; with none: {pct(s.share_inhabited_coverage0)}. Wellbeing among inhabited places comes from a regional figure for {String(s.wb_admin1 ?? "n/a")}, a national figure for {String(s.wb_national ?? "n/a")}, and is missing for {String(s.wb_none ?? "n/a")}.
              </p>
              <CoverageTable dims={[...m.hazards, ...m.dimensions]} res={res} />
            </div>
          );
        })}
      </section>

      <section>
        <H2>Spot checks</H2>
        <p>Four places the pipeline prints on every build so an obviously wrong layer is caught before the map ships (SPEC §8.5).</p>
        {resList.map((res) => (
          <SpotChecks key={res} m={m} res={res} />
        ))}
      </section>

      <section>
        <H2>Sources</H2>
        <p>
          All data is open-licensed with attribution. {m.non_commercial && "This project is non-commercial; "}
          {shdi ? `${shdi.name} is used under terms that allow non-commercial use only.` : ""}
        </p>
        <Wide>
          <table className="mt-2 w-full min-w-[44rem] text-xs">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-1 pr-2">Source</th>
                <th className="py-1 pr-2">Vintage</th>
                <th className="py-1 pr-2">Licence</th>
                <th className="py-1 pr-2">Processing</th>
                <th className="py-1">Checked</th>
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
                  <td className="py-1">{verifiedWords(s.verified)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Wide>
      </section>

      <section>
        <H2>Known gaps</H2>
        {resList.map((res) => {
          const gaps = m.known_gaps?.[res] ?? {};
          const entries = Object.entries(gaps).filter(([, v]) => Array.isArray((v as { countries_without_data?: unknown }).countries_without_data));
          return (
            <div key={res} className="mt-2">
              {resList.length > 1 && <h3 className="font-medium">{scaleName(res)}</h3>}
              <ul className="list-disc space-y-1 pl-5">
                {entries.map(([id, v]) => {
                  const g = v as { countries_without_data: string[]; n_countries_without_data: number; share_inhabited_hexes_missing: number | null };
                  return (
                    <li key={id}>
                      <span className="font-medium">{names.get(id) ?? id}</span>: {pct(g.share_inhabited_hexes_missing)} of inhabited places have no value; {g.n_countries_without_data} countries have none at all
                      {g.countries_without_data.length ? ` (${g.countries_without_data.join(", ")}${g.n_countries_without_data > g.countries_without_data.length ? ", …" : ""})` : ""}.
                    </li>
                  );
                })}
                {!entries.length && <li>No gap statistics in this build.</li>}
              </ul>
            </div>
          );
        })}
        <p className="mt-2">Extreme heat: {HEAT_CAVEAT} A humid-heat layer (heat index or wet-bulb temperature) is planned once its source is checked.</p>
        <p className="mt-2">Small islands and thin coasts whose hexagon centre falls at sea are not on the map (Reykjavik&rsquo;s own hexagon, for example); the spot check falls back to the nearest land hexagon and says so.</p>
      </section>

      <section className="text-xs text-muted">
        Built {m.built_at ?? "n/a"}
        {m.published_at ? `, published ${m.published_at}` : ""}. Source code and the full specification are on GitHub at{" "}
        <a className="underline hover:text-ink" href={REPO} rel="noreferrer">
          saj-sudo/livability-map
        </a>
        .
      </section>
    </main>
  );
}
