# Deploying (SPEC §13.14, §13.24, §13.38, §15.14)

Static-first: the pipeline publishes the tile archives + `manifest.json` to Cloudflare R2 and the
Next.js static export goes to Cloudflare Pages. No servers, no database, no per-request work.

## One-time setup (Cloudflare dashboard)

1. **R2 bucket**: create `livability-tiles` (or any name; put it in `.env` as `R2_BUCKET`).
   Attach a custom domain (R2 → bucket → Settings → Custom Domains); `r2.dev` URLs are
   rate-limited and fine only for testing. Put the public base URL in `.env` as
   `R2_PUBLIC_BASE_URL` and `NEXT_PUBLIC_DATA_BASE` (both are required).
2. **R2 S3 API token** (R2 → Manage API tokens → Object Read & Write on that bucket): copy the
   Access Key ID, Secret Access Key and Account ID into `.env` (`R2_ACCESS_KEY_ID`,
   `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`).
3. **Account API token** for Pages (My Profile → API Tokens → Create → "Cloudflare Pages: Edit"):
   `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` in `.env`.
4. `R2_ALLOWED_ORIGINS`: the Pages URL(s) and `http://localhost:3000`, comma-separated. The
   `publish` stage writes the CORS policy for range requests (`range`, `if-match` allowed;
   `etag`, `content-length`, `content-range`, `accept-ranges` exposed).

## Each release

```bash
uv run python -m pipeline --res 4 --res 5 all         # ... tiles, validate, publish (r2 when .env is set)
uv run python -m pipeline validate --release          # optional: the release checks without uploading
cd web && npm run deploy                                # builds against the live R2 manifest, then Pages
```

What `publish --target r2` does, in order (it stops at the first failure and the live map stays
as it was):

1. Refuses a fixture, `--bbox` or partial build, unverified sources, and anything `validate`
   rejects. The comparison baseline is the `manifest.json` the bucket serves now: a layer that
   lost more than 5% of its inhabited hexes fails the release. Pass `--max-drop 0.2` (say) only
   for a drop you can explain, and write the reason in SPEC §11.
2. Uploads each archive as `<archive>.<sha12>.pmtiles` with `Cache-Control: immutable`. An
   archive already in the bucket under that key is not uploaded again; nothing is overwritten.
3. Sets CORS and fetches the first 16 KB of a new archive with a `Range` header. Its printed
   diagnosis explains the common failures (no 206, missing `Access-Control-Allow-Origin`,
   Hotlink Protection).
4. Uploads `manifest.json` (`no-cache`) naming the new keys, and a dated copy under
   `manifests/`. A copy is kept locally at `data/out/published/manifest.json`.

`npm run deploy` then reads the live `manifest.json`, refuses it if it is a fixture, bbox or
local build or names an archive the bucket does not serve, builds the site against it, drops
`out/data/` (tiles never go to Pages) and deploys with a pinned wrangler.

**Rolling back:** in the Cloudflare dashboard, Pages → the project → Deployments → an earlier
deployment → "Rollback". Its pages name the archives that were live then, and those are still in
the bucket, so the site is whole again at once. The browser never reads the bucket's
`manifest.json`; only the next `npm run deploy` does. Before deploying again, point it back by
copying the matching `manifests/<built_at>.json` over `manifest.json` in the bucket.

**Storage:** every release adds about 0.7 GB of archives. Delete old `*.pmtiles` keys by hand
once no Pages deployment you might roll back to names them.

## Local development

```bash
uv run python -m pipeline --fixtures --res 4 all      # validates, then publishes to web/public/data/
cd web && npm run dev                                   # http://localhost:3000
```

The app reads `/data/hexes.pmtiles` from its own origin unless `NEXT_PUBLIC_DATA_BASE` is set.
