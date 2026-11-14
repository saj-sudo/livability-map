import { expect, test, type Page } from "@playwright/test";

// UX flows on the fixture build (2026-11-14 fixes): search keeps the searched name, the compare
// picking mode (banner, Escape, empty clicks, outlines in step with the panel), and the phone
// sheet (legend at peek, tabs). Same network rules as smoke.spec.ts: basemap blocked, CSP
// violations and page errors fail the test.

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

/** Open the map, dismiss the intro and wait until the fixture hexes are drawn. */
async function openMap(page: Page, url = CEDAR) {
  await page.goto(url);
  await page.getByRole("dialog").getByRole("button", { name: "Skip" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "background map is unavailable" })).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1500); // tiles decoded and drawn
  const map = page.getByRole("application");
  return { map, box: (await map.boundingBox())! };
}

const outlined = async (page: Page) => ((await page.getByRole("application").getAttribute("data-outlined")) ?? "").split(",").filter(Boolean);

test("search keeps the searched place name in the panel", async ({ page }) => {
  const seen = await watch(page);
  await openMap(page, "/?lat=42&lng=12&z=4");
  const box = page.getByRole("combobox", { name: "Search a city or region" });
  await box.fill("Aquila");
  await page.getByRole("option", { name: /L'Aquila/ }).click();
  const heading = page.getByRole("heading", { level: 2, name: "Near L'Aquila" });
  await expect(heading).toBeVisible({ timeout: 15_000 });
  await expect(heading).toBeFocused(); // keyboard users land on the new place
  const panel = page.getByRole("region", { name: "Near L'Aquila" });
  await expect(panel).toContainText(/B-Mid/);
  await expect(panel).toContainText(/people in this ~[\d,.]+ km² area/);
  await expect(panel).not.toContainText(/res \d|in a res/);
  await expect(panel).toContainText(/This area in B-Mid/);
  expect(await outlined(page)).toHaveLength(1);
  expect(seen.violations).toEqual([]);
  expect(seen.errors).toEqual([]);
});

test("compare: a banner while picking, Escape cancels, outlines follow the panel", async ({ page }) => {
  const seen = await watch(page);
  const { box } = await openMap(page);
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await page.mouse.click(cx, cy);
  const placeA = page.getByRole("heading", { level: 2 }).filter({ hasText: /B-Mid|Cedaria/ });
  await expect(placeA).toBeVisible({ timeout: 10_000 });
  expect(await outlined(page)).toHaveLength(1);
  const a = (await outlined(page))[0];

  // start picking: a persistent banner; Escape cancels and keeps place A
  await page.getByRole("button", { name: "Compare with another place" }).click();
  const banner = page.getByTestId("pick-banner");
  await expect(banner).toContainText("Pick a second place on the map, or search for one.");
  await page.waitForTimeout(4500); // longer than a transient hint lives
  await expect(banner).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(banner).toBeHidden();
  await expect(placeA).toBeVisible();
  expect(await outlined(page)).toEqual([a]);

  // pick again; an empty click (east of the fixture world) does nothing to place A
  await page.getByRole("button", { name: "Compare with another place" }).click();
  await page.mouse.click(box.x + box.width - 40, cy);
  await expect(banner).toBeVisible();
  await expect(placeA).toBeVisible();
  expect(await outlined(page)).toEqual([a]);

  // a second place: the comparison opens and both are outlined
  await page.mouse.click(cx - 80, cy + 10);
  await expect(page.getByRole("heading", { name: "Side by side" })).toBeVisible();
  await expect(banner).toBeHidden();
  await expect.poll(() => outlined(page)).toHaveLength(2);
  const both = await outlined(page);
  expect(both[0]).toBe(a);
  await expect(page.getByRole("region", { name: "Compare two places" })).toContainText("Environment today");

  // Cancel button on a re-pick, then swap, then Escape closes the comparison, then the panel
  await page.getByRole("button", { name: "Change second place" }).click();
  await banner.getByRole("button", { name: "Cancel" }).click();
  await expect(banner).toBeHidden();
  await page.getByRole("button", { name: "Swap" }).click();
  await expect.poll(() => outlined(page)).toEqual([both[1], both[0]]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "Side by side" })).toBeHidden();
  await expect.poll(() => outlined(page)).toEqual([both[1]]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { level: 2 }).filter({ hasText: /B-Mid|Cedaria|B-/ })).toHaveCount(0);
  await expect.poll(() => outlined(page)).toEqual([]);
  expect(seen.violations).toEqual([]);
  expect(seen.errors).toEqual([]);
});

test.describe("phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the sheet shows the colour key at peek and its tabs work", async ({ page }) => {
    const seen = await watch(page);
    await page.goto(CEDAR);
    const intro = page.getByRole("dialog");
    await expect(intro).toContainText("Layers tab");
    await intro.getByRole("button", { name: "Skip" }).click();
    await expect(page.getByRole("button", { name: "How to read this map" })).toBeFocused();

    const legend = page.getByTestId("compact-legend");
    await expect(legend).toBeVisible();
    await expect(legend).toContainText("more climate exposure");
    await expect(legend).toBeInViewport();

    const layers = page.getByRole("tab", { name: "Layers" });
    const placeTab = page.getByRole("tab", { name: /Place/ });
    await expect(layers).toHaveAttribute("aria-selected", "true");
    await layers.click();
    await expect(page.getByRole("tabpanel")).toContainText("Climate exposure × wellbeing");
    await expect(page.getByRole("tabpanel")).toContainText("Mark places missing some hazard data");

    // arrow keys move between tabs
    await layers.focus();
    await page.keyboard.press("ArrowRight");
    await expect(placeTab).toHaveAttribute("aria-selected", "true");
    await expect(placeTab).toBeFocused();
    await expect(page.getByRole("tabpanel")).toContainText("Tap a hexagon");
    await page.keyboard.press("ArrowLeft");
    await expect(layers).toHaveAttribute("aria-selected", "true");

    const handle = page.getByRole("button", { name: /panels/ });
    const hb = (await handle.boundingBox())!;
    expect(hb.height).toBeGreaterThanOrEqual(24);
    expect(seen.violations).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});
