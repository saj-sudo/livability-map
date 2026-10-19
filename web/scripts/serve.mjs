// A static server for the e2e smoke test (SPEC §13.40): serves out/ the way Cloudflare does what
// matters here, i.e. it applies out/_headers (so the CSP is enforced in the browser), answers
// Range requests with 206 (PMTiles reads byte ranges) and serves 404.html for unknown paths.
//   node scripts/serve.mjs [outDir=out] [port=3100]
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const [outDir = "out", port = "3100"] = process.argv.slice(2);
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".txt": "text/plain", ".woff2": "font/woff2", ".pmtiles": "application/octet-stream" };

/** [{ pattern, headers: [[name, value]] }] from a `_headers` file. */
function parseHeaders(text) {
  const rules = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    if (!/^\s/.test(line)) rules.push({ pattern: line.trim(), headers: [] });
    else if (rules.length) {
      const i = line.indexOf(":");
      rules.at(-1).headers.push([line.slice(0, i).trim(), line.slice(i + 1).trim()]);
    }
  }
  return rules;
}

const matches = (pattern, path) => (pattern.endsWith("*") ? path.startsWith(pattern.slice(0, -1)) : pattern === path);
const rules = existsSync(join(outDir, "_headers")) ? parseHeaders(readFileSync(join(outDir, "_headers"), "utf8")) : [];

createServer((req, res) => {
  const url = new URL(req.url, "http://localhost");
  let path = decodeURIComponent(url.pathname);
  let file = normalize(join(outDir, path));
  if (!file.startsWith(normalize(outDir))) return res.writeHead(403).end();
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  let status = 200;
  if (!existsSync(file)) {
    status = 404;
    file = join(outDir, "404.html");
    path = "/404.html";
  }
  for (const r of rules) if (matches(r.pattern, path)) for (const [k, v] of r.headers) res.setHeader(k, v);
  res.setHeader("Content-Type", TYPES[extname(file)] ?? "application/octet-stream");
  res.setHeader("Accept-Ranges", "bytes");
  const size = statSync(file).size;
  const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
  if (range && status === 200) {
    const start = range[1] === "" ? Math.max(0, size - Number(range[2])) : Number(range[1]);
    const end = range[1] !== "" && range[2] !== "" ? Math.min(Number(range[2]), size - 1) : size - 1;
    if (start > end || start >= size) return res.writeHead(416, { "Content-Range": `bytes */${size}` }).end();
    res.writeHead(206, { "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": end - start + 1 });
    return createReadStream(file, { start, end }).pipe(res);
  }
  res.writeHead(status, { "Content-Length": size });
  if (req.method === "HEAD") return res.end();
  createReadStream(file).pipe(res);
}).listen(Number(port), () => console.log(`serving ${outDir} on http://localhost:${port}`));
