// Cloudflare Pages `_headers` for the static export (SPEC §13.40). Run after `next build`:
//   node scripts/headers.mjs [outDir=out] [dataOrigin]
// deploy.mjs does this with the R2 origin; the e2e smoke test does it with no data origin
// (tiles from the same origin) and serves the result with scripts/serve.mjs.
//
// Each HTML page gets its own Content-Security-Policy whose script-src lists the sha256 of that
// page's inline scripts (the theme boot script and Next's payload scripts), so no inline script
// runs unless the build put it there and nothing loads from origins the map does not use.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

export const BASEMAP_ORIGINS = ["https://tiles.openfreemap.org"];

/** sha256 CSP sources for every inline <script> in a page. */
export function inlineScriptHashes(html) {
  const out = [];
  for (const m of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)) {
    if (!m[1]) continue;
    out.push(`'sha256-${createHash("sha256").update(m[1], "utf8").digest("base64")}'`);
  }
  return [...new Set(out)];
}

/** The Content-Security-Policy for one page. */
export function pageCsp({ scriptHashes, dataOrigin = null, basemapOrigins = BASEMAP_ORIGINS }) {
  const connect = ["'self'", ...(dataOrigin ? [dataOrigin] : []), ...basemapOrigins];
  return [
    "default-src 'self'",
    `script-src 'self' ${scriptHashes.join(" ")}`.trim(),
    // React and MapLibre set style attributes; styles cannot run code
    "style-src 'self' 'unsafe-inline'",
    `connect-src ${connect.join(" ")}`,
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

/** URL path a page is served at ("index.html" -> "/", "about/index.html" -> "/about/"). */
export function pagePath(relPath) {
  const p = relPath.split(sep).join("/");
  if (p === "index.html") return "/";
  if (p.endsWith("/index.html")) return `/${p.slice(0, -"index.html".length)}`;
  return `/${p}`;
}

const COMMON = [
  "X-Content-Type-Options: nosniff",
  "Referrer-Policy: strict-origin-when-cross-origin",
  "Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "X-Frame-Options: DENY",
  "Cross-Origin-Opener-Policy: same-origin",
];

/** The whole `_headers` file for a list of { path, hashes } pages. */
export function headersFile(pages, dataOrigin = null) {
  const lines = ["/*", ...COMMON.map((h) => `  ${h}`), "", "/_next/static/*", "  Cache-Control: public, max-age=31536000, immutable", ""];
  for (const { path, hashes } of [...pages].sort((a, b) => a.path.localeCompare(b.path))) {
    lines.push(path, `  Content-Security-Policy: ${pageCsp({ scriptHashes: hashes, dataOrigin })}`, "");
  }
  return lines.join("\n");
}

function htmlFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) {
      if (name !== "data" && name !== "_next") out.push(...htmlFiles(p));
    } else if (name.endsWith(".html")) out.push(p);
  }
  return out;
}

/** Scan a built `out/` and write `out/_headers`. Returns the page list. */
export function writeHeaders(outDir, dataOrigin = null) {
  const pages = htmlFiles(outDir).map((f) => ({ path: pagePath(relative(outDir, f)), hashes: inlineScriptHashes(readFileSync(f, "utf8")) }));
  writeFileSync(join(outDir, "_headers"), headersFile(pages, dataOrigin));
  return pages;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [outDir = "out", origin = null] = process.argv.slice(2);
  const pages = writeHeaders(outDir, origin ? new URL(origin).origin : null);
  console.log(`_headers: CSP for ${pages.length} pages (${pages.map((p) => p.path).join(", ")})`);
}
