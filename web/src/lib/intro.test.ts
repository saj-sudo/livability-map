import { describe, expect, it } from "vitest";
import { dismissIntro, INTRO_KEY, INTRO_STEPS, introSteps, nextStep, shouldShowIntro } from "./intro";

function fakeStorage(initial: Record<string, string> = {}, throws = false): Storage {
  const data = { ...initial };
  const boom = () => {
    throw new Error("blocked");
  };
  return { getItem: (k: string) => (throws ? boom() : (data[k] ?? null)), setItem: (k: string, v: string) => (throws ? boom() : void (data[k] = v)) } as unknown as Storage;
}

describe("first-visit intro (localStorage only)", () => {
  it("has three short steps", () => {
    expect(INTRO_STEPS).toHaveLength(3);
    for (const s of INTRO_STEPS) expect(s.body.length).toBeLessThan(320);
  });

  it("shows once, then remembers the dismissal", () => {
    const s = fakeStorage();
    expect(shouldShowIntro(s)).toBe(true);
    dismissIntro(s);
    expect(s.getItem(INTRO_KEY)).toBe("1");
    expect(shouldShowIntro(s)).toBe(false);
  });

  it("copes with blocked storage", () => {
    const blocked = fakeStorage({}, true);
    expect(shouldShowIntro(blocked)).toBe(true);
    expect(() => dismissIntro(blocked)).not.toThrow();
    expect(shouldShowIntro(null)).toBe(true);
  });

  it("steps forward and closes after the last", () => {
    expect(nextStep(0)).toBe(1);
    expect(nextStep(2)).toBeNull();
  });

  it("says where the key is on a phone and on a wide screen", () => {
    expect(introSteps(false)[0].body).toContain("panel on the left");
    expect(introSteps(true)[0].body).toContain("Layers tab");
    expect(introSteps(true)[0].body).not.toContain("left");
    expect(introSteps(true)[2].body).toMatch(/^Tap/);
    for (const s of introSteps(true)) expect(s.body.length).toBeLessThan(320);
    for (const s of introSteps(true)) expect(s.body).not.toContain("\u2014"); // no em dashes
  });
});
