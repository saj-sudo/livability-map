import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The redesign's measures of success (SPEC §13.50, docs/design-redesign-plan.md) on the fixture
// build: the default key shows one variable, "What matters to you" is one tap from the first
// phone view, an old link keeps its meaning, the place panel leads with a few lines, the share
// card never lists places, and an axe scan finds nothing. Same network rules as smoke.spec.ts:
// the basemap is blocked, CSP violations and page errors fail the test.

const TOWN = "lat=42.5&lng=13&z=6"; // a fixture town (pipeline/fixtures/make_fixtures.py)

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

/** Open a map URL with the first-visit card already seen, and wait until the hexes are drawn. */
async function openSeen(page: Page, url: string) {
  await page.addInitScript(() => window.localStorage.setItem("lm.intro", "1"));
  await page.goto(url);
  await expect(page.getByRole("alert").filter({ hasText: "background map is unavailable" })).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1500);
}

const clean = (seen: { violations: string[]; errors: string[] }) => {
  expect(seen.violations).toEqual([]);
  expect(seen.errors).toEqual([]);
};

/** axe over the whole page: WCAG 2.x A and AA. The map canvas is one opaque application. */
async function scan(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).exclude(".maplibregl-canvas").analyze();
  return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

test("a bare address opens one variable: the key is one ramp, the plate carries year and pathway", async ({ page }) => {
  const seen = await watch(page);
  await page.goto("/");
  const intro = page.getByRole("dialog");
  await expect(intro).toContainText("Where do you want to start?");
  await intro.getByRole("button", { name: "Skip" }).click();
  const key = page.getByTestId("map-key");
  await expect(key).toContainText("Projected exposure");
  await expect(key).toContainText("less exposed");
  await expect(key).toContainText("more exposed");
  await expect(key).not.toContainText(/wellbeing/i); // one variable
  await expect(key).not.toContainText(/thriving|struggling/i); // the key never gives a verdict
  const plate = page.getByTestId("plate");
  await expect(plate.getByRole("heading", { level: 1 })).toHaveText("Climate exposure, 2050");
  await expect(plate).toContainText("RCP4.5 / SSP2-4.5");
  await expect(page).toHaveURL(/view=exp/);
  clean(seen);
});

test("an old link with a position and no view= still shows the bivariate view", async ({ page }) => {
  const seen = await watch(page);
  await openSeen(page, `/?${TOWN}`);
  await expect(page.getByTestId("map-key")).toContainText("Exposure beside wellbeing");
  await expect(page.getByTestId("map-key")).toContainText("wellbeing here is one national figure");
  await expect(page).toHaveURL(/view=bivar/); // and from now on the view is always written
  clean(seen);
});

test("the intro's second door opens My priorities with presets first", async ({ page }) => {
  const seen = await watch(page);
  await page.goto("/");
  await page.getByRole("dialog").getByRole("button", { name: /What matters to you/ }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByTestId("plate").getByRole("heading", { level: 1 })).toHaveText("Fit with your priorities");
  const presets = page.getByRole("group", { name: "Presets" });
  await expect(presets.getByRole("button", { name: "Early career" })).toBeVisible();
  await presets.getByRole("button", { name: "Early career" }).click();
  await expect(page.getByTestId("plate").getByRole("heading", { level: 1 })).toHaveText("Fit with Early career");
  await expect(page.getByTestId("map-key")).toContainText("stronger fit");
  await expect(page.getByText("Climate hazards, 2050").first()).toBeVisible(); // a folded group
  await expect(page.getByText(/\d+ weighted/).first()).toBeVisible();
  clean(seen);
});

test("the place panel leads with at most five lines and keeps every measure one step away", async ({ page }) => {
  const seen = await watch(page);
  await openSeen(page, `/?${TOWN}&view=priorities&preset=early`);
  const box = (await page.getByRole("application").boundingBox())!;
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  const panel = page.getByRole("region").filter({ has: page.getByTestId("lead-lines") });
  await expect(panel).toBeVisible({ timeout: 10_000 });
  const lines = panel.getByTestId("lead-lines").getByRole("listitem");
  expect(await lines.count()).toBeGreaterThanOrEqual(2);
  expect(await lines.count()).toBeLessThanOrEqual(5);
  await expect(panel.getByTestId("lead-lines")).toContainText("Climate in 2050");
  await expect(panel.getByTestId("lead-lines")).toContainText(/A (weak|partial|strong) fit\./);
  await expect(panel.getByTestId("lead-lines")).not.toContainText(/\d+\/100/); // the fit is a band in words
  const all = panel.getByTestId("all-measures");
  await expect(all.getByText("Environment today")).toBeHidden();
  await all.locator("summary").click();
  await expect(all.getByText("Environment today")).toBeVisible();
  await expect(all.getByText(/^Sources \(\d+\)$/)).toBeVisible();
  await expect(all).toContainText(/more is (worse|better)/);
  expect(await scan(page)).toEqual([]);
  clean(seen);
});

test("a shared link opens with a card that names the weights and never lists places", async ({ page }) => {
  const seen = await watch(page);
  await page.goto(`/?${TOWN}&view=priorities&preset=early&share=1`);
  const card = page.getByTestId("share-card");
  await expect(card).toContainText("A map for: Early career");
  await expect(card).toContainText("early-career job market ×3");
  await expect(card).toContainText("not a ranking of places");
  await expect(card).toContainText("2050");
  await expect(page.getByText("Where do you want to start?")).toBeHidden(); // one card at a time
  await card.getByRole("button", { name: "Look at this map" }).click();
  await expect(card).toBeHidden();
  await expect(page).not.toHaveURL(/share=/);
  clean(seen);
});

for (const path of ["/", "/about/", "/methodology/"]) {
  test(`axe finds nothing on ${path}`, async ({ page }) => {
    await watch(page);
    if (path === "/") await openSeen(page, path);
    else await page.goto(path);
    for (const scheme of ["light", "dark"] as const) {
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), scheme);
      expect(await scan(page), scheme).toEqual([]);
    }
  });
}

test.describe("phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("What matters to you is one tap from the first view, and the page is one screen tall", async ({ page }) => {
    const seen = await watch(page);
    await openSeen(page, "/");
    const height = () => page.evaluate(() => [document.documentElement.scrollHeight, window.innerHeight]);
    let [doc, view] = await height();
    expect(doc).toBe(view); // the sheet never makes the document scroll
    const door = page.getByRole("button", { name: "What matters to you" });
    await expect(door).toBeInViewport();
    expect((await door.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await door.tap(); // the one tap
    await expect(page.getByRole("group", { name: "Presets" }).getByRole("button", { name: "Early career" })).toBeInViewport();
    await expect(page.getByTestId("plate").getByRole("heading", { level: 1 })).toHaveText("Fit with your priorities");
    [doc, view] = await height();
    expect(doc).toBe(view);
    // 44px touch targets: tabs, doors, presets
    for (const target of [page.getByRole("tab", { name: "Layers" }), page.getByRole("button", { name: "Climate in 2050" }), page.getByRole("button", { name: "Early career" })]) {
      expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await scan(page)).toEqual([]);
    clean(seen);
  });

  test("a notice never lands on the zoom control", async ({ page }) => {
    await watch(page);
    await openSeen(page, `/?${TOWN}&view=exp`);
    const notice = (await page.getByRole("alert").filter({ hasText: "background map is unavailable" }).boundingBox())!;
    const zoom = (await page.getByRole("button", { name: "Zoom in" }).boundingBox())!;
    const overlap = notice.x < zoom.x + zoom.width && zoom.x < notice.x + notice.width && notice.y < zoom.y + zoom.height && zoom.y < notice.y + notice.height;
    expect(overlap).toBe(false);
    expect(zoom.height).toBeGreaterThanOrEqual(44);
  });
});
