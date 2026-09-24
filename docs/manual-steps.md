# Manual steps

Things the pipeline cannot do for itself: downloads behind a registration or a browser check,
credentials, and permissions that need a person to ask. Each item says what to do, where the file
goes, and what to run (or ask Claude to run) afterwards. Keep this page current: add an item when
a session hits a wall, and move it to **Done** with the date once it is handled.

Last updated: 2026-09-24.

## Open

| # | Item | Unlocks | Effort |
|---|---|---|---|
| 1 | [Cloudflare R2 + Pages credentials](#1-cloudflare-r2--pages-credentials) | the public site | 20 min |
| 2 | [Global Data Lab downloads](#2-global-data-lab-downloads-one-registration) | regional wellbeing everywhere; school and health outside the US / OECD | 15 min |
| 3 | [HUD Fair Market Rents workbook](#3-hud-fair-market-rents-workbook) | US rent | 2 min |
| 4 | [MEDSL county election returns](#4-medsl-county-election-returns) | US political lean | 5 min |
| 5 | [Tanzania census permission](#5-tanzania-census-permission) | ward-level Tanzania data | email + wait |
| 6 | [Gridded Relative Deprivation Index](#6-gridded-relative-deprivation-index-nasa-earthdata-login) | 1 km deprivation worldwide | 10 min |
| 7 | [Kenya census boundaries](#7-kenya-census-boundaries) | sub-county / sub-location Kenya data | email + wait |
| 8 | [Afrobarometer permission](#8-afrobarometer-permission) | LGBTQ+ tolerance by region in ~35 African countries | email + wait |
| 9 | [UNICEF Giga API key](#9-unicef-giga-api-key) | school locations and school connectivity | 10 min |
| 10 | [DHS modeled surfaces](#10-dhs-modeled-surfaces) | 5 km education, vaccination, wealth surfaces | 10 min + read terms |
| 11 | [WPdx licence confirmation](#11-wpdx-licence-confirmation) | removes a caveat on the `water` layer | email + wait |
| 12 | [Flip the repo public](#12-flip-the-repo-public) | the public GitHub repo | 2 min |
| 13 | [Optional: rewrite the author email on two early commits](#13-optional-rewrite-the-author-email-on-two-early-commits) | keeps a personal Gmail out of the public history | 15 min, before item 12 |

Items 2-4 and 6 only need a file saved in the right place. After any of them, run
`uv run python -m pipeline fetch` to record checksums, then ask Claude to rebuild the dimension
(the commands are listed per item).

---

### 1. Cloudflare R2 + Pages credentials

Needed for `publish --target r2` and `npm run deploy` (SPEC §13.24).

1. In the Cloudflare dashboard, create an R2 bucket (for example `livability-map`) and an R2 API
   token with object read and write on that bucket.
2. Connect a custom domain to the bucket (public access), or note the r2.dev URL.
3. Create a Pages project for the web app.
4. Create `.env` in the repo root (it is gitignored) with:
   `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`,
   `R2_PUBLIC_BASE_URL` (the public bucket URL), `R2_ALLOWED_ORIGINS` (the Pages URL and
   `http://localhost:3000`), `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CF_PAGES_PROJECT`,
   and `NEXT_PUBLIC_DATA_BASE` (same as `R2_PUBLIC_BASE_URL`). `.env.example` lists the rest.

Then: `uv run python -m pipeline publish --target r2` (uploads the three archives and the
manifest, sets CORS, checks range requests), then `cd web && npm run deploy`.

### 2. Global Data Lab downloads (one registration)

Free registration at https://globaldatalab.org/register/ (non-commercial use; the project is
non-commercial, SPEC §13.13).

| Save as | From | Feeds |
|---|---|---|
| `data/raw/gdl_shdi/SHDI-data.csv` | https://globaldatalab.org/shdi/download/ , "Subnational HDI Data v10.2" CSV | wellbeing: regional instead of national on ~94% of hexes |
| `data/raw/gdl_shdi_regions/GDL-Shapefiles.zip` | https://globaldatalab.org/shdi/shapefiles/ , the GDL shapefile zip (V6.x) | the region polygons for everything in this row and below |
| any name under `data/raw/gdl_education/` | GDL "Education & Work" dataset download (all countries, CSV) | school: years of schooling, attendance (new source) |
| any name under `data/raw/gdl_health/` | GDL "Health" dataset download (all countries, CSV) | health: vaccination, child mortality, stunting (new source) |

Then, for the first two: `uv run python -m pipeline dims --only wb`, then `score`, `export`,
`tiles`, `publish`. The education and health files need a loader and a §15 entry first: ask
Claude to wire them (the region polygons and the `polygon_centroid` joiner already exist).

### 3. HUD Fair Market Rents workbook

huduser.gov answers scripts with an empty page (a bot check), so this needs a browser. Open
https://www.huduser.gov/portal/datasets/fmr/fmr2026/FY26_FMRs.xlsx and save it as
`data/raw/hud_fmr/FY26_FMRs.xlsx` (about 377 KB). The file there now is empty and must be replaced.

Then: `uv run python -m pipeline dims --only rent`, then `score`, `export`, `tiles`, `publish`.

### 4. MEDSL county election returns

Harvard Dataverse asks for a guestbook entry. Either fill the four `DATAVERSE_GUESTBOOK_*` values
in `.env` and run `uv run python -m pipeline fetch --only medsl_county_pres`, or open
https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/VOQCHQ , download
`countypres_2000-2024.csv` (original format) and save it under `data/raw/medsl_county_pres/`.

Then: `uv run python -m pipeline dims --only pol`, then `score`, `export`, `tiles`, `publish`.

### 5. Tanzania census permission

**Status:** the data is downloaded and joins cleanly, but it cannot ship. The National Bureau of
Statistics publishes no open licence ("Copyright ©2023 National Bureau of Statistics. All Rights
Reserved", https://www.nbs.go.tz/pages/copyright-statement), and SPEC invariant 4 requires a
confirmed licence.

**What we have** (in `data/raw/tz_nbs_census_2022/` and `data/raw/tz_ward_boundaries/`, from the
official census portal https://sensa.nbs.go.tz and its GeoServer):
- 2022 census population, households and household size for all 4,344 wards and shehia
  (joins 4,343 of 4,344 to the NBS ward polygons);
- council-level (195 councils) household amenities, housing materials and tenure, employment and
  literacy.

**Ask:** written permission to publish values derived from the 2022 PHC ward and council tables
on a free, non-commercial map, with attribution. A draft:

> To: the National Bureau of Statistics, Tanzania (see https://www.nbs.go.tz/ for the current
> contact address)
>
> Subject: Permission to reuse 2022 Population and Housing Census ward and council tables
>
> Dear NBS team,
>
> I am building a free, non-commercial web map that shows projected climate hazards alongside
> present-day living conditions, so people can compare places (livability-map). I would like to
> use the 2022 Population and Housing Census results published on sensa.nbs.go.tz: population and
> households by ward, and household amenities (electricity, water, sanitation), housing, employment
> and literacy by council, together with the census ward and council boundaries.
>
> The map would show values aggregated to hexagonal cells, never individual records, with the
> citation "Source: National Bureau of Statistics, 2022 Population and Housing Census" on the map
> and its methodology page. Could you confirm whether this reuse is permitted, and under what
> attribution or conditions?
>
> Thank you,
> Saj Chandoo

**After a yes:** save the reply (or its wording) and ask Claude to wire it: a §15 entry quoting
the permission, a loader for the ward and council tables, and a new "household services"
dimension (the council amenities do not fit any current dimension). Population alone adds little,
because the map already has 1 km population.

### 6. Gridded Relative Deprivation Index (NASA Earthdata login)

CIESIN / NASA SEDAC, 1 km, global, CC BY 4.0, version 1 (2010-2020). The download needs a free
NASA Earthdata account (https://urs.earthdata.nasa.gov/users/new); the licence allows
redistribution.

Download the GRDI v1 GeoTIFF from the SEDAC dataset page ("Global Gridded Relative Deprivation
Index (GRDI), v1") and save it under `data/raw/ciesin_grdi/`. Then ask Claude to wire it as a
`raster_mean` source (likely into income mix, labelled; note it is partly built from subnational
HDI and night lights, so it overlaps with wellbeing).

### 7. Kenya census boundaries

**Status:** KNBS publishes 2019 population for 8,932 sub-locations (xlsx, downloaded to
`data/raw/ke_knbs_census_2019/`) and socio-economic tables by sub-county in a PDF, but no
matching 2019 boundaries are public. The best polygons (2002 sub-locations on HDX) match only
58% of rows. KNBS terms: "All Rights Reserved ... Extracts may be published if the source is
duly acknowledged."

**Ask** KNBS (https://www.knbs.or.ke/) for the 2019 census sub-location and sub-county boundary
files and confirmation that derived values may be published with acknowledgement. Low priority:
with boundaries, Kenya would get sub-county jobs, housing, water and sanitation.

### 8. Afrobarometer permission

Afrobarometer data are copyrighted ("acknowledge the source"); the public files carry a region
code and include a question on accepting homosexual neighbours, which could give a regional
LGBTQ+ tolerance value for about 35 African countries (the `lgbtq` dimension is US-only today).
Ask Afrobarometer (https://www.afrobarometer.org/) whether publishing regional aggregates of
that question on the map is permitted. If yes, ask Claude to wire it at admin1.

### 9. UNICEF Giga API key

Giga (UNICEF / ITU) maps schools and their connectivity worldwide; only three countries are on
HDX. Request an API key at https://giga.global/ (Giga Maps / data access) and check the licence
terms that come with it. Then ask Claude to wire school locations (school access) and
connectivity (a second internet source). Note: OSM-derived school data would be ODbL.

### 10. DHS modeled surfaces

The DHS Program's Spatial Data Repository (https://spatialdata.dhsprogram.com/modeled-surfaces/)
has 5 km surfaces for education, vaccination and wealth, behind an email form. The terms are in
a README inside each download. Download one country, read the README, and note whether
publishing derived values is allowed. If it is, save the surfaces under
`data/raw/dhs_modeled_surfaces/` and ask Claude to wire them.

### 11. WPdx licence confirmation

The `water` layer uses the global WPdx+ export (https://data.waterpointdata.org/dataset/eqje-vguj),
which states no licence for users. WPdx publishes the same country data on HDX as CC BY-SA, so the
map records CC BY-SA 4.0 and labels the derived values share-alike (SPEC §13.37). Ask WPdx
(https://www.waterpointdata.org/ , contact form) to confirm the licence for users of the global
export. If they say CC BY 4.0, update `license` on `wpdx_water_points` in `pipeline/sources.yaml`
and drop the share-alike label; nothing needs rebuilding.

### 12. Flip the repo public

First confirm `LICENSE` (MIT) is on `main`: open https://github.com/saj-sudo/livability-map/blob/main/LICENSE .
If it 404s, merge the branch that adds it (`claude/portfolio-github-updates-ik5ico`) first. If
you want item 13, do it before this one: once the repo is public, anyone can clone the old
history.

Then on GitHub: the repo, **Settings**, **General**, scroll to **Danger Zone**, **Change
visibility**, **Change to public**, and confirm with the repo name.

A check of the tracked files on 2026-09-24 found no personal emails, Windows user paths, tokens or
keys (`.env.example` holds only empty keys and placeholders). The one personal detail left is in
git history, item 13.

### 13. Optional: rewrite the author email on two early commits

Two commits from 2026-09-20/21, `c1156a0` (Session 1) and `e25784a` (CI install fix), carry a
personal Gmail as author and committer. Every other commit uses the GitHub noreply address.
Replacing it means rewriting history:

- It changes the SHA of those two commits **and every commit after them**, so it needs a
  force-push to `main`. Any SHA quoted elsewhere (PR descriptions, notes, this item) stops
  resolving.
- It is safe only because the history is days old, the repo is private and nobody has forked it.
  Merge or delete every other branch first, and re-clone (or `git fetch` then
  `git reset --hard origin/main`) on the laptop afterwards.
- It does not clean everything: GitHub keeps pull-request refs (`refs/pull/*`) that you cannot
  delete, so the old commits stay reachable through the merged PRs' pages. Removing those needs a
  request to GitHub Support (https://support.github.com/, "remove cached views / PR refs").

Commands, in a fresh clone outside the working copy (Git Bash):

```bash
pip install git-filter-repo
git clone https://github.com/saj-sudo/livability-map.git livability-map-rewrite
cd livability-map-rewrite
OLD=$(git log -1 --format=%ae c1156a0)           # the personal address; kept out of this file on purpose
printf '%s\n' "Saj Chandoo <263086808+saj-sudo@users.noreply.github.com> <$OLD>" > ../mailmap.txt
git filter-repo --mailmap ../mailmap.txt
git log --format='%ae %ce' | sort -u          # expect only noreply addresses
git remote add origin https://github.com/saj-sudo/livability-map.git   # filter-repo removes it
git push --force origin main
```

GitHub's branch protection, if on, has to allow the force-push for that one push. Then delete
`../mailmap.txt` and the `livability-map-rewrite` folder.

---

## Done

- 2026-09-23: Norway, Canada, Australia, France, Germany, the Netherlands, England, the EU grid:
  no manual steps needed (all direct downloads, verified in SPEC §15).
