// Light / dark theme (SPEC §13.10 visual identity; invariant 7: no cookies, no accounts). The
// choice lives in localStorage only, never in the URL, so a shared link never forces a theme.
// Pure functions here; the DOM side (data-theme attribute, event) is in components/useTheme.ts.

import { BASEMAP_STYLES } from "./config";

export type Theme = "light" | "dark";
export const THEMES: readonly Theme[] = ["light", "dark"];
export const THEME_KEY = "lm.theme";
/** DOM event dispatched on window when the theme changes (the map listens to swap basemaps). */
export const THEME_EVENT = "lm:theme";

const isTheme = (v: unknown): v is Theme => v === "light" || v === "dark";

/** Explicit choice wins; otherwise the system preference; otherwise light. */
export function resolveTheme(stored: string | null, prefersDark: boolean): Theme {
  if (isTheme(stored)) return stored;
  return prefersDark ? "dark" : "light";
}

export function basemapStyleFor(theme: Theme): string {
  return BASEMAP_STYLES[theme];
}

/** localStorage can throw (private windows, blocked storage); a failure just means "no choice". */
export function readStoredTheme(storage: Storage | null | undefined): Theme | null {
  try {
    const v = storage?.getItem(THEME_KEY) ?? null;
    return isTheme(v) ? v : null;
  } catch {
    return null;
  }
}

export function writeStoredTheme(storage: Storage | null | undefined, theme: Theme): void {
  try {
    storage?.setItem(THEME_KEY, theme);
  } catch {
    // storage blocked: the theme still applies for this page view
  }
}

/**
 * The script inlined at the top of <body> so the first paint already has the right theme. Kept
 * as a string here so it stays next to the key and the resolution rule it mirrors.
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var s=localStorage.getItem(${JSON.stringify(THEME_KEY)});var d=window.matchMedia("(prefers-color-scheme: dark)").matches;var t=(s==="light"||s==="dark")?s:(d?"dark":"light");document.documentElement.dataset.theme=t;}catch(e){}})();`;
