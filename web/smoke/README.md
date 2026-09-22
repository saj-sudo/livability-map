# PMTiles smoke page (SPEC §16, Session 5 gate)

A bare MapLibre GL JS v6 page that reads `hexes.pmtiles` with HTTP range requests, colours
inhabited hexes by the bivariate class and prints a clicked hex's attributes. No build step:
pinned CDN scripts with subresource integrity.

```bash
uv run python -m pipeline --fixtures --res 4 publish --target local   # -> web/public/data/
npx serve web -l 8000                                                  # a static server that supports byte ranges
# then open
http://localhost:8000/smoke/?url=http://localhost:8000/public/data/hexes.pmtiles&lat=42&lng=12&z=5
# and, after publish --target r2:
http://localhost:8000/smoke/?url=https://<R2_PUBLIC_BASE_URL>/hexes.pmtiles
```

Python's `http.server` does not support range requests and will not work here; `npx serve`,
`npx wrangler pages dev web` or any real web server does. The on-page log shows the archive
header (zoom range, bounds, tile count), the layer list and any tile errors.
