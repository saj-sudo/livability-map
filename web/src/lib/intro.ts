// First-visit card (SPEC §10, §13.50): one card, two doors, shown once. The only state is one
// localStorage flag; no cookies, no accounts (invariant 7). Pure here; the card is
// components/Intro.tsx.

import type { ViewId } from "./url";

export const INTRO_KEY = "lm.intro";

export interface IntroDoor {
  view: ViewId;
  title: string;
  body: string;
}

export const INTRO_TITLE = "Where do you want to start?";

/** The two ways in. The first is the default view; the second is the map's own idea. */
export const INTRO_DOORS: IntroDoor[] = [
  { view: "exp", title: "Climate in 2050", body: "Projected heat, flooding and water stress, place by place." },
  { view: "priorities", title: "What matters to you", body: "Pick a starting point such as Early career or Raising kids, then adjust it." },
];

/** The three things a newcomer must know, in one line under the doors. */
export const INTRO_FINE = "Grey means no data, never zero risk. Every number has a source. This map does not tell you where to live.";

/** Show the intro when the flag is absent; storage may be unavailable (private mode). */
export function shouldShowIntro(storage: Storage | null | undefined): boolean {
  try {
    return storage?.getItem(INTRO_KEY) !== "1";
  } catch {
    return true;
  }
}

export function dismissIntro(storage: Storage | null | undefined): void {
  try {
    storage?.setItem(INTRO_KEY, "1");
  } catch {
    // storage blocked: the intro is simply shown again next time
  }
}
