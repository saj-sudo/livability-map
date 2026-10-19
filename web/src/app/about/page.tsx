export const metadata = { title: "About — livability-map" };

// SPEC §3 in plain language (non-goals), the non-commercial statement (§13.13) and prior art (§18).
export default function About() {
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-8 text-sm leading-relaxed">
      <h1 className="text-2xl font-semibold">About</h1>
      <p>
        This is a free, global map that puts projected climate hazard exposure (extreme heat, riverine flood, coastal flood and water stress under one moderate scenario for 2050) beside present-day wellbeing and a set of life dimensions you can weight yourself: jobs, transit, schools, LGBTQ+ presence, political lean, income mix, housing cost and healthcare. It is built only from open-licensed data, on hexagons a few tens of kilometres across.
      </p>
      <h2 className="text-lg font-semibold">It does not recommend where to live</h2>
      <p>
        The map shows evidence, shows its sources and shows its gaps. There is no ranking, no &ldquo;top ten places&rdquo; feed and no single livability number decided for you. The default view needs no weighting; the priorities view exposes every weight as a slider and computes the result in your browser. Where a layer is missing, the hex says so and is drawn differently; missing data is never treated as zero risk.
      </p>
      <p>
        Racial and ethnic composition (US census tracts) appears in the place panel as context, with its source. It is deliberately not something you can weight or filter by: ranking neighbourhoods by who lives there is steering, and this map does not do it.
      </p>
      <h2 className="text-lg font-semibold">What it is not</h2>
      <ul className="list-disc space-y-1 pl-5">
        <li>Not property- or street-level: hexes are large on purpose. Insurers and specialist services do parcel-level work; this map does not.</li>
        <li>Not real-time: the hazards are projections for a stated scenario and horizon, always shown in the interface.</li>
        <li>Not a forecast of certainties: one moderate pathway is shown; other scenarios are future work.</li>
        <li>Not a substitute for local knowledge: regional wellbeing and national fallbacks smooth over real differences, and the resolution badge on every value says how coarse it is.</li>
        <li>Not complete: several life dimensions exist only for the United States, and some countries have no subnational wellbeing data. The methodology page lists the gaps.</li>
      </ul>
      <h2 className="text-lg font-semibold">Privacy and licensing</h2>
      <p>
        No accounts, no trackers, no analytics scripts. The only requests your browser makes are for the tiles, the basemap and, when you search, a list of place names served from this site (Natural Earth populated places, public domain, and geoBoundaries regions, CC BY 4.0). Fonts are bundled with the site. Two small preferences live in your browser&rsquo;s local storage and nowhere else: the light or dark theme, and whether you have seen the three-step intro. There are no cookies. All data sources are open-licensed with attribution; Global Data Lab&rsquo;s Subnational HDI is used under its non-commercial terms, so this project is non-commercial for the foreseeable future. Code is MIT.
      </p>
      <h2 className="text-lg font-semibold">Prior art</h2>
      <p>
        Global future-climate maps (Probable Futures, Climate Impact Explorer, WRI Aqueduct) carry no wellbeing and no weighting. Weighted &ldquo;where should I live&rdquo; tools use present-day climate only. US climate-plus-social tools are framed as &ldquo;who needs help&rdquo; and are US-only. This map is the open, global combination of the two.
      </p>
      <h2 className="text-lg font-semibold">How to cite</h2>
      <p>livability-map (2026), open-source climate and wellbeing map, built from the sources listed on the methodology page. Please cite the underlying datasets as their publishers request.</p>
    </main>
  );
}
