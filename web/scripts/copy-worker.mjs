// MapLibre GL JS v6 loads its worker by URL, so bundled apps must serve the worker file
// themselves (SPEC §15.13). Copy it from node_modules into public/ before dev and build so the
// worker always matches the installed library version.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const candidates = ["maplibre-gl-worker.mjs", "maplibre-gl-csp-worker.js", "maplibre-gl-worker.js"];
const distDir = join(here, "..", "node_modules", "maplibre-gl", "dist");
const src = candidates.map((f) => join(distDir, f)).find((p) => existsSync(p));
if (!src) {
  console.error("maplibre-gl worker file not found in", distDir, "(looked for", candidates.join(", "), ")");
  process.exit(1);
}
const dest = join(here, "..", "public", "maplibre-gl-worker.mjs");
mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log("copied", src, "->", dest);
