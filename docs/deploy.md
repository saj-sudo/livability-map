# Deploying (SPEC §13.14, §13.24, §15.14)

Static-first: the pipeline publishes `hexes.pmtiles` + `manifest.json` to Cloudflare R2 and the
Next.js static export goes to Cloudflare Pages. No servers, no database, no per-request work.

## One-time setup (Cloudflare dashboard)

1. **R2 bucket**: create `livability-tiles` (or any name; put it in `.env` as `R2_BUCKET`).
   Attach a custom domain (R2 → bucket → Settings → Custom Domains); `r2.dev` URLs are
   rate-limited and fine only for testing. Put the public base URL in `.env` as
   `R2_PUBLIC_BASE_URL` and `NEXT_PUBLIC_DATA_BASE`.
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
uv run python -m pipeline --res 4 --res 5 all         # ... export, tiles, publish (r2 when .env is set)
cd web && npm run deploy                                # next build + wrangler pages deploy out
```

`publish --target r2` uploads the archive first, then the manifest, sets CORS, and fetches the
first 16 KB of the archive with a `Range` header to confirm byte serving and CORS. Its printed
diagnosis explains the common failures (no 206, missing `Access-Control-Allow-Origin`,
Hotlink Protection).

## Local development

```bash
uv run python -m pipeline --fixtures --res 4 all      # publishes to web/public/data/
cd web && npm run dev                                   # http://localhost:3000
```

The app reads `/data/hexes.pmtiles` from its own origin unless `NEXT_PUBLIC_DATA_BASE` is set.
