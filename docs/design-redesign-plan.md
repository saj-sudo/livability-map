# Design redesign plan: livability map

Written 2026-11-18. This is the plan for the map's part of a design pass across Saj's builds. It
holds what a review saw, what is proposed, what would move, and where the work stands. `SPEC.md`
stays the source of truth: anything here that ships changes the spec first (§9, §10, §13.10), and
§16 "Next steps" points at this file. Update the status section at the end of every sitting.

## Verdict: rethink the default view; rework the look

The ethics are the strongest of any of the builds (missing data is never zero, every number has a
source, no ranking). The limit is structure: the default view works against the product's own
stance, and the one thing no other map does is hidden. After that, the look: it reads as a stock
map with panels, not as an atlas.

## What the review saw

Not deployed, so this was judged from `docs/screenshots/session-9/` and `docs/screenshots/2026-11-14/`
(some are stale: they predate humid heat) and from the components in `web/src/components/`. The
first step of the mockup sitting is to run the fixture world and look at the real thing.

- **The default view reads as a ranking of countries.** The bivariate default paints Europe blue
  and Africa and the Middle East red. The blue axis is mostly a national wellbeing figure (the
  place panel says so: "the national figure, not this region's"), so whole countries are coloured
  "safe and thriving" or "exposed and struggling" before the reader has asked anything. That is
  the ranking SPEC §3 refuses to make, delivered by colour.
  See `docs/screenshots/session-9/light-bivariate.jpg`.
- **A nine-colour key is the first thing a newcomer has to learn.** The phone sheet's two-line key
  ("Redder: more climate exposure. Bluer: higher wellbeing.") is clearer than the desktop grid.
- **"My priorities" is seventh in a list of layers.** It is the differentiator: presets such as
  "Early career" and "Queer and looking for community", weights the reader sets, a map that
  recolours on the spot.
- **The place panel is 30 or more rows of bars** after a good one-sentence summary. Bar colour
  flips meaning row to row ("Armed conflict 99/100" red, "Internet 90/100" green, "Travel time
  2/100" grey), so each row has to be decoded.
- **Desktop crowding.** With Layers and the place panel open, the two take about 600 of 1280px.
  See `docs/screenshots/session-9/inspector-priorities.jpg`.
- **The key changes meaning between themes** (the top-right cell is dark plum in light and pink in
  dark), and the mid-tones sit close to the no-data grey.
- **The look.** Default OpenFreeMap basemap with place labels in several scripts colliding with
  the hexes, floating shadowed cards, stock zoom buttons. The Newsreader wordmark and the
  hairlines are the only atlas cues.
- **A number that brushes the no-single-number rule.** "My priorities" shows a 0 to 100 match per
  place ("69/100").

### What the real screens added (2026-11-19)

Seen on the fixture build with the real OpenFreeMap basemap (it loads in the cloud container):

- **Dark theme: basemap roads and borders draw over the hexes** as thick black lines, and labels
  switch to capitals.
- **Phone: the document is taller than the screen** (1,471px on an 844px viewport): the bottom
  sheet hangs below `.map-shell`, so the whole page can scroll.
- **Phone place panel: two hazard rows and their caveats fill the sheet at half height.**
- **The key itself ranks:** the desktop grid captions two corners "safe and thriving" and "exposed
  and struggling".
- "My priorities" is now eighth of eight layers (humid heat was added after the review).
- The "pick a second place" banner covers the zoom control on a phone; the intro card covers the
  key it describes; the dashed outline for national wellbeing is nearly invisible at z6.
- Correction to the review: the single-layer ramps do not change meaning between themes (the end
  that stands out from the ground is "more" in both). The bivariate grid's hues do change identity.
- There is no combined-exposure view today (hazards are separate views), so proposal 1 needs a new
  view id appended to `VIEWS`.
- Old links: `serializeState` omits `view` when it is the default but always writes `lat`, `lng`
  and `z`. So a bare address can open the new default while a link with a position and no `view=`
  keeps meaning bivariate (option B in the mockup).

## Proposal (what the mockup will show)

1. **A simpler default.** One variable first ("Climate exposure in 2050"), with the two-variable
   view one step in. Wellbeing that is only a national figure is shown as a country outline or a
   pattern, not as a hex fill that looks local.
   Likely files: `web/src/lib/url.ts` (the default view), `web/src/components/{MapApp,Panel,Legend}.tsx`,
   `web/src/lib/palette.ts`, `web/src/lib/expressions.ts`.
2. **"My priorities" up front.** The first-run card offers a choice: start with climate, or start
   with what matters to you. Presets are the first thing in that path; sliders sit collapsed by
   group behind them.
   Likely files: `web/src/components/{Intro,PrioritiesPanel}.tsx`, `web/src/lib/intro.ts`, `web/src/presets.ts`.
3. **A place panel that leads.** Three to five plain lines first, then "All measures". Bars keep
   one meaning; direction is said in words.
   Likely files: `web/src/components/Inspector.tsx`, `web/src/lib/{inspect,chart,summary}.ts`.
4. **An atlas look.** A quiet basemap with few labels, a plate title on the map ("Heat, 2050"), a
   docked key that means the same in both themes, a scale bar. SPEC §13.10 already names the
   "Atlas" identity; this makes it visible.
   Likely files: `web/src/components/MapView.tsx`, `web/src/lib/{config,palette}.ts`, `web/src/app/globals.css`.
5. **A shareable "my map".** Pick a preset, the world recolours, and the view can be shared with
   the preset name, the key and a sources line. No list of places, ever.

## What would move (each needs Saj's yes on the mockup)

- The bivariate view: from the default to one step in.
- The 0 to 100 "matches your priorities" number: to words or bands ("strong, partial, weak fit"),
  with exact numbers kept per dimension. Saj's call against SPEC invariant 6.
- The seven-item Layers list: regrouped so "My priorities" is not the last entry.
- The full list of measures in the place panel: behind "All measures".

## Rules this touches

- SPEC invariants: no ranking and no single livability number; missing data is never zero and must
  look different from a low score; every number traceable; scenario and horizon always visible.
- Composition dimensions (race) stay context only: no slider, never in the composite.
- `w=` order in the URL is append-only, so old links keep their meaning. A changed default view
  must not change what an existing link shows.
- The per-page CSP: no remote fonts, scripts or images. Basemap stays OpenFreeMap (never Mapbox or
  ArcGIS).
- Copy keeps "rank among inhabited places" and "match with your priorities" distinct, and keeps
  the heat caveats.
- SPEC first, then code; CLAUDE.md and the §17 checkboxes updated at the end of the session.

## Measures of success

- The default key shows one variable.
- "My priorities" is one tap from the first view on a phone.
- No whole country reads as one colour because of a national figure.
- The e2e suite passes with the basemap blocked, plus an axe scan with no violations.

## Finish items to fold into the same build

From the code audit of 2026-11-18:
- `viewport-fit=cover` (the sheet's safe-area padding resolves to 0 today), `theme-color` per
  scheme, notices moved off the zoom control, fallback basemap colours aligned to `--paper`.
- A named type scale with a 12px floor (24 uses of 11px, plus the attribution).
- Palette guard tests that measure what the comments claim: lightness monotone along each row and
  column, a minimum distance between no-data grey and every cell, corners separable under protan
  and deutan simulation.
- 44px touch targets on phones (close, tabs, chips, sliders are 20 to 32px today).
- `<main>` and a skip link on the map page; the legend's hover text is no longer a live region;
  the search input gets the standard focus ring; an axe scan in e2e (already open in §16).
- Queued behind these: selecting a hex from the keyboard, and a table view of the data that is
  never a sorted ranking.

## Stages and status

| Stage | State | Link | Date |
|---|---|---|---|
| Review from screenshots and code | Done | this file | 2026-11-18 |
| Run the fixture world and capture real screens | Done: 32 captures (8 screens, 390x844 and 1440x900, both themes) | `docs/mockups/2026-11-19-redesign/shots/` | 2026-11-19 |
| Mockup | Done: today beside proposed, with the decisions list | https://claude.ai/artifact/EQ5RpTqgA7DpQS2SHCmkE5 (source: `docs/mockups/2026-11-19-redesign/index.html`) | 2026-11-19 |
| Saj picks a direction | Done: "1 yes, 2 bands, 3 yes, 4 yes, invariant yes, links B" | SPEC §13.50 | 2026-11-19 |
| Build and pull request | Built; pull request open, waiting on review | https://github.com/saj-sudo/livability-map/pull/16 (after screenshots: `docs/mockups/2026-11-19-redesign/after/`) | 2026-11-19 |
| Check on real data | Not started: manual-steps item 23 (Saj's laptop) | `docs/manual-steps.md` | |

### What the build did against the measures of success (2026-11-19)

- The default key shows one variable: **passed** (e2e: one ramp, no wellbeing, no verdict words).
- "My priorities" is one tap from the first view on a phone: **passed** (e2e: the "What matters
  to you" door in the sheet's peek, 44px tall).
- No whole country reads as one colour because of a national figure: **passed on the fixture
  world, not proven on real data** (manual-steps item 23). National hexes take an ochre
  exposure-only colour; the mockup's rust steps failed the new palette test and were replaced.
- The e2e suite passes with the basemap blocked, plus an axe scan with no violations: **passed**
  (18 tests; axe in both themes, on a phone and with the place panel open).

Differences from the mockup, all recorded in SPEC §13.50: the exposure-only colour is ochre, not
rust; the climate lead line states combined exposure as an average of hazard ranks (it is not
itself a rank, so "more exposed than two thirds of places" would have been wrong); the country
outline is the basemap's own border, so it is absent when the basemap is blocked.

Still queued: selecting a hex from the keyboard, and a table view that is never a sorted ranking.

## Starting a session on this build

Paste this into a fresh session that has this repository attached:

> Read `docs/design-redesign-plan.md`, `CLAUDE.md` and SPEC.md §3, §9, §10 and §13.10 in this
> repo. We are doing the next open stage in the plan's status table, and only that stage. If the
> stage is the mockup: build the fixture world (`uv run python -m pipeline --fixtures --res 4 all`),
> run the web app, capture today's screens at 390 by 844 and 1440 by 900 in both themes, and
> publish a mockup page that shows today's screens beside the proposed ones, with the "what would
> move" list, then stop for my pick. If the stage is the build: change the spec first, build what
> I picked, check the measures of success, open a pull request with before and after screenshots,
> and update the status table.
