// MapLibre GL JS v6 loads its worker by URL, and the worker module imports a shared chunk next
// to it, so both must be served by the app (SPEC §15.13). They are copied from node_modules into
// public/ before dev and build so they always match the installed library version.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const distDir = join(here, "..", "node_modules", "maplibre-gl", "dist");
const publicDir = join(here, "..", "public");
mkdirSync(publicDir, { recursive: true });
for (const name of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  const src = join(distDir, name);
  if (!existsSync(src)) {
    console.error("missing", src, "- MapLibre changed its dist layout; update scripts/copy-worker.mjs");
    process.exit(1);
  }
  copyFileSync(src, join(publicDir, name));
  console.log("copied", name, "-> public/");
}
