import { expect, test, type Page } from "@playwright/test";

// Smoke test of the built site on the fixture world (SPEC §13.40). The basemap host is blocked
// in every test so CI never depends on a third party, which also exercises the plain-background
// fallback. Every page must run under its CSP with no violation.

const CEDAR = "/?lat=42.5&lng=13&z=6"; // a fixture town (pipeline/fixtures/make_fixtures.py)

async function watch(page: Page) {
  const violations: string[] = [];
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const t = m.text();
    if (/Content Security Policy/i.test(t)) violations.push(t);
    else if (!/openfreemap|ERR_FAILED|Failed to load resource/i.test(t)) errors.push(t);
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.route("https://tiles.openfreemap.org/**", (r) => r.abort());
  return { violations, errors };
}

test("the map draws the fixture hexes and a click opens the place panel", async ({ page }) => {
  const seen = await watch(page);
  const ranges: number[] = [];
  page.on("response", (r) => {
    if (r.url().includes(".pmtiles")) ranges.push(r.status());
  });
  await page.goto(CEDAR);
  await page.getByRole("dialog").getByRole("button", { name: "Skip" }).click(); // the first-visit intro
  await expect(page.getByRole("alert").filter({ hasText: "background map is unavailable" })).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => ranges.includes(206), { timeout: 20_000 }).toBe(true);
  const map = page.getByRole("application");
  await page.waitForTimeout(1500); // tiles decoded and drawn
  const box = (await map.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.getByRole("heading", { level: 2 }).filter({ hasText: /B-Mid|Cedaria/ })).toBeVisible({ timeout: 10_000 });
  expect(seen.violations).toEqual([]);
  expect(seen.errors).toEqual([]);
});

test("without WebGL 2 the page explains instead of drawing a blank map", async ({ page }) => {
  await page.addInitScript(() => {
    const orig = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, kind: string, ...rest: unknown[]) {
      return kind === "webgl2" ? null : (orig as (...a: unknown[]) => unknown).call(this, kind, ...rest);
    } as typeof orig;
  });
  await watch(page);
  await page.goto(CEDAR);
  await expect(page.getByRole("alert").filter({ hasText: "needs WebGL 2" })).toBeVisible();
});

test("an unreachable tile archive leaves a notice that stays", async ({ page }) => {
  await watch(page);
  await page.route("**/data/*.pmtiles", (r) => r.fulfill({ status: 404, body: "not found" }));
  await page.goto(CEDAR);
  const notice = page.getByRole("alert").filter({ hasText: "map data could not be loaded" });
  await expect(notice).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(5000); // longer than a transient hint lives
  await expect(notice).toBeVisible();
});

for (const path of ["/methodology/", "/about/"]) {
  test(`${path} renders under its CSP`, async ({ page }) => {
    const seen = await watch(page);
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(seen.violations).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
}
