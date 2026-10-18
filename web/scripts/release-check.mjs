// What `npm run deploy` checks before it builds the site against the live manifest (SPEC §13.38).
// Pure so vitest covers it; deploy.mjs does the network and the build.

/**
 * Problems that make a manifest unfit to deploy: the live R2 manifest must be a real, whole-world
 * build published to R2, naming at least one tile archive by a content-addressed key.
 * @param {Record<string, any> | null | undefined} m
 * @returns {string[]}
 */
export function releaseProblems(m) {
  if (!m || typeof m !== "object") return ["no manifest.json was found at NEXT_PUBLIC_DATA_BASE"];
  const problems = [];
  if (m.fixtures) problems.push("the manifest is from the fixture world, not a real build");
  if (m.bbox) problems.push(`the manifest is from a --bbox subregion build (${m.bbox})`);
  if (m.publish_target !== "r2") problems.push(`the manifest was published to '${m.publish_target ?? "nowhere"}', not r2: run \`python -m pipeline publish --target r2\``);
  const tiles = Object.entries(m.tiles ?? {});
  if (!tiles.length) problems.push("the manifest lists no tile archive");
  for (const [name, t] of tiles) {
    if (!/^[\w-]+\.[0-9a-f]{12}\.pmtiles$/.test(t?.key ?? "")) problems.push(`archive ${name} has key '${t?.key}', not a content-addressed key from publish --target r2`);
  }
  if (!Array.isArray(m.dimensions) || !m.dimensions.length) problems.push("the manifest lists no dimensions");
  return problems;
}
