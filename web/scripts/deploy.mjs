// Deploy the static export to Cloudflare Pages (SPEC §13.14, §13.24, §13.38).
// Reads ../.env (never printed): CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CF_PAGES_PROJECT,
// NEXT_PUBLIC_DATA_BASE. Usage: npm run deploy [-- --branch preview]
//
// The site is built against the manifest R2 serves now (the one `publish --target r2` switched
// last), never a local one, so the deployed pages name exactly the content-addressed archives
// that are live. The archives are checked to exist first, public/data is kept out of the
// upload (Pages serves the app, R2 serves the tiles), and _headers gets a CSP per page.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { writeHeaders } from "./headers.mjs";
import { releaseProblems } from "./release-check.mjs";

const WRANGLER = "wrangler@4.146.0"; // pinned: a deploy tool should not change under a release

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const root = join(web, "..");
const envPath = join(root, ".env");
const env = { ...process.env };
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !line.trim().startsWith("#") && !env[m[1]]) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}
const fail = (msg) => {
  console.error(`Cannot deploy: ${msg}`);
  process.exit(1);
};
const missing = ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CF_PAGES_PROJECT", "NEXT_PUBLIC_DATA_BASE"].filter((k) => !env[k]);
if (missing.length) fail(`set ${missing.join(", ")} in ${envPath} (see .env.example; NEXT_PUBLIC_DATA_BASE is the R2 public URL).`);
const base = env.NEXT_PUBLIC_DATA_BASE.replace(/\/$/, "");
if (!/^https:\/\//.test(base)) fail(`NEXT_PUBLIC_DATA_BASE must be the https URL of the R2 bucket, got ${base}`);
const branchIdx = process.argv.indexOf("--branch");
const branch = branchIdx > -1 ? process.argv[branchIdx + 1] : "main";

const resp = await fetch(`${base}/manifest.json`, { headers: { "Cache-Control": "no-cache" } }).catch((err) => fail(`could not read ${base}/manifest.json (${err})`));
if (!resp.ok) fail(`${base}/manifest.json answered HTTP ${resp.status}; run \`python -m pipeline publish --target r2\` first`);
const manifest = await resp.json();
const problems = releaseProblems(manifest);
if (problems.length) fail(`the live manifest is not a release:\n  - ${problems.join("\n  - ")}`);
for (const t of Object.values(manifest.tiles)) {
  const head = await fetch(`${base}/${t.key}`, { method: "HEAD" }).catch(() => null);
  if (!head?.ok) fail(`${base}/${t.key} is not reachable (HTTP ${head?.status ?? "error"}); the manifest names an archive the bucket does not serve`);
}
console.log(`deploying the build of ${manifest.built_at} (published ${manifest.published_at}): ${Object.values(manifest.tiles).map((t) => t.key).join(", ")}`);

const cache = join(web, ".release");
mkdirSync(cache, { recursive: true });
const manifestPath = join(cache, "manifest.json");
writeFileSync(manifestPath, JSON.stringify(manifest));
const buildEnv = { ...env, LIVABILITY_MANIFEST: manifestPath };

const run = (cmd, args) => {
  console.log(">", cmd, args.join(" "));
  const r = spawnSync(cmd, args, { stdio: "inherit", env: buildEnv, cwd: web, shell: process.platform === "win32" });
  if (r.status !== 0) process.exit(r.status ?? 1);
};
run("npm", ["run", "build"]);
// public/data (a local publish) is copied into out/ by Next; it must not reach Pages
rmSync(join(web, "out", "data"), { recursive: true, force: true });
// security headers: a CSP per page that allows only its own inline scripts and the map's origins
const pages = writeHeaders(join(web, "out"), new URL(base).origin);
console.log(`_headers written: CSP for ${pages.map((p) => p.path).join(", ")}`);
run("npx", ["--yes", WRANGLER, "pages", "deploy", "out", "--project-name", env.CF_PAGES_PROJECT, "--branch", branch, "--commit-dirty=true"]);
