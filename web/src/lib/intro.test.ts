import { describe, expect, it } from "vitest";
import { dismissIntro, INTRO_DOORS, INTRO_FINE, INTRO_KEY, INTRO_TITLE, shouldShowIntro } from "./intro";
import { VIEWS } from "./url";

function fakeStorage(initial: Record<string, string> = {}, throws = false): Storage {
  const data = { ...initial };
  const boom = () => {
    throw new Error("blocked");
  };
  return { getItem: (k: string) => (throws ? boom() : (data[k] ?? null)), setItem: (k: string, v: string) => (throws ? boom() : void (data[k] = v)) } as unknown as Storage;
}

describe("first-visit intro (localStorage only)", () => {
  it("is one question with two doors: the default view, then My priorities (SPEC §13.50)", () => {
    expect(INTRO_TITLE).toMatch(/\?$/);
    expect(INTRO_DOORS.map((d) => d.view)).toEqual(["exp", "priorities"]);
    for (const d of INTRO_DOORS) {
      expect(VIEWS).toContain(d.view);
      expect(d.body.length).toBeLessThan(120);
    }
  });

  it("says the three things a newcomer must know", () => {
    expect(INTRO_FINE).toMatch(/no data, never zero risk/);
    expect(INTRO_FINE).toMatch(/source/);
    expect(INTRO_FINE).toMatch(/does not tell you where to live/);
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
});
