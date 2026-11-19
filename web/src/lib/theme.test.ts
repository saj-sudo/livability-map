import { describe, expect, it } from "vitest";
import { basemapStyleFor, readStoredTheme, resolveTheme, THEME_KEY, writeStoredTheme } from "./theme";

// a Storage stand-in that can be told to throw (private mode, blocked storage)
function fakeStorage(initial: Record<string, string> = {}, throws = false): Storage {
  const data = { ...initial };
  const boom = () => {
    throw new Error("storage blocked");
  };
  return {
    getItem: (k: string) => (throws ? boom() : (data[k] ?? null)),
    setItem: (k: string, v: string) => (throws ? boom() : void (data[k] = v)),
    removeItem: (k: string) => void delete data[k],
    clear: () => void 0,
    key: () => null,
    length: 0,
  } as unknown as Storage;
}

describe("theme resolution (no cookies, no URL)", () => {
  it("prefers an explicit stored choice over the system preference", () => {
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("falls back to the system preference, then light", () => {
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme(null, false)).toBe("light");
    expect(resolveTheme("garbage", true)).toBe("dark");
  });

  it("maps each theme to our own style on OpenFreeMap's tiles and glyphs", () => {
    for (const theme of ["light", "dark"] as const) {
      const style = basemapStyleFor(theme);
      expect(JSON.stringify(style.sources)).toMatch(/tiles\.openfreemap\.org\/planet/);
      expect(style.glyphs).toMatch(/tiles\.openfreemap\.org\/fonts/);
      expect(style.name).toContain(theme);
    }
    expect(JSON.stringify(basemapStyleFor("light").layers)).not.toBe(JSON.stringify(basemapStyleFor("dark").layers));
  });

  it("reads and writes localStorage defensively", () => {
    const s = fakeStorage();
    expect(readStoredTheme(s)).toBeNull();
    writeStoredTheme(s, "dark");
    expect(readStoredTheme(s)).toBe("dark");
    expect(s.getItem(THEME_KEY)).toBe("dark");
    const blocked = fakeStorage({}, true);
    expect(readStoredTheme(blocked)).toBeNull();
    expect(() => writeStoredTheme(blocked, "light")).not.toThrow();
  });
});
