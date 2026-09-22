// First-visit intro (SPEC §10): three short steps, shown once. The only state is one
// localStorage flag; no cookies, no accounts (invariant 7). Pure here; the card is
// components/Intro.tsx.

export const INTRO_KEY = "lm.intro";

export interface IntroStep {
  title: string;
  body: string;
}

export const INTRO_STEPS: IntroStep[] = [
  {
    title: "What the colours mean",
    body: "Each hexagon is coloured by two things at once: projected climate exposure in 2050 (redder means more) and present-day wellbeing (bluer means higher). Grey means no data, never zero risk. The legend on the left is the key.",
  },
  {
    title: "Make it yours",
    body: "Pick My priorities to weight what matters to you: jobs, schools, housing cost, heat and more. The map recolours in your browser, and a dimension missing on a hex simply drops out of its average.",
  },
  {
    title: "Every number has a source",
    body: "Click a hexagon for its values, scores and the datasets behind them, then compare it with another place. Where the data is coarse or missing, the map says so.",
  },
];

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

/** Next step index, clamped; null when past the last step (the card closes). */
export function nextStep(current: number, total: number = INTRO_STEPS.length): number | null {
  return current + 1 < total ? current + 1 : null;
}
