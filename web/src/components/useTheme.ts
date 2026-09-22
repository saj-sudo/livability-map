"use client";

// DOM side of the theme (SPEC §13.10): the `data-theme` attribute on <html> is the single source
// of truth (set before paint by THEME_BOOT_SCRIPT in layout.tsx), localStorage remembers an
// explicit choice, and a window event tells the map to swap its basemap.

import { useCallback, useSyncExternalStore } from "react";
import { readStoredTheme, resolveTheme, THEME_EVENT, writeStoredTheme, type Theme } from "../lib/theme";

const MEDIA = "(prefers-color-scheme: dark)";

export function getDomTheme(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

/** Apply a theme now, remember it, and notify listeners (the map, the legend). */
export function applyTheme(theme: Theme, remember = true): void {
  document.documentElement.dataset.theme = theme;
  if (remember) writeStoredTheme(window.localStorage, theme);
  window.dispatchEvent(new CustomEvent<Theme>(THEME_EVENT, { detail: theme }));
}

function subscribe(onChange: () => void): () => void {
  const mq = window.matchMedia(MEDIA);
  // follow the system while the person has not chosen explicitly
  const onSystem = () => {
    if (readStoredTheme(window.localStorage) === null) applyTheme(resolveTheme(null, mq.matches), false);
  };
  window.addEventListener(THEME_EVENT, onChange);
  mq.addEventListener("change", onSystem);
  return () => {
    window.removeEventListener(THEME_EVENT, onChange);
    mq.removeEventListener("change", onSystem);
  };
}

/** [theme, setTheme]; renders "light" on the server and corrects itself after hydration. */
export function useTheme(): [Theme, (t: Theme) => void] {
  const theme = useSyncExternalStore<Theme>(subscribe, getDomTheme, () => "light");
  const set = useCallback((t: Theme) => applyTheme(t), []);
  return [theme, set];
}
