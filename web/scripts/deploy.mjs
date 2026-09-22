// Deploy the static export to Cloudflare Pages (SPEC §13.14, §13.24, §16 Session 7).
// Reads ../.env (never printed): CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CF_PAGES_PROJECT,
// NEXT_PUBLIC_DATA_BASE. Usage: npm run deploy [-- --branch preview]
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const envPath = join(root, ".env");
const env = { ...process.env };
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && !line.trim().startsWith("#") && !env[m[1]]) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}
const missing = ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CF_PAGES_PROJECT"].filter((k) => !env[k]);
if (missing.length) {
  console.error(`Cannot deploy: set ${missing.join(", ")} in ${envPath} (see .env.example).`);
  process.exit(1);
}
if (!env.NEXT_PUBLIC_DATA_BASE) {
  console.warn("NEXT_PUBLIC_DATA_BASE is not set: the deployed site will look for tiles at /data on its own origin, which Pages does not serve. Set it to the R2 public URL.");
}
const branchIdx = process.argv.indexOf("--branch");
const branch = branchIdx > -1 ? process.argv[branchIdx + 1] : "main";

const run = (cmd, args) => {
  console.log(">", cmd, args.join(" "));
  const r = spawnSync(cmd, args, { stdio: "inherit", env, cwd: join(here, ".."), shell: process.platform === "win32" });
  if (r.status !== 0) process.exit(r.status ?? 1);
};
run("npm", ["run", "build"]);
run("npx", ["wrangler@4", "pages", "deploy", "out", "--project-name", env.CF_PAGES_PROJECT, "--branch", branch, "--commit-dirty=true"]);
