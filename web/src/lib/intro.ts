// First-visit intro (SPEC §10): three short steps, shown once. The only state is one
// localStorage flag; no cookies, no accounts (invariant 7). Pure here; the card is
// components/Intro.tsx.

export const INTRO_KEY = "lm.intro";

export interface IntroStep {
  title: string;
  body: string;
}

/** Where the colour key is: the left panel on a wide screen, the Layers tab of the bottom
 *  sheet on a phone. */
export const legendWhere = (phone: boolean): string => (phone ? "The key is in the Layers tab at the bottom of the screen." : "The key is in the Layers panel on the left.");

/** The three steps; the first says where the key is, which differs on a phone. */
export function introSteps(phone = false): IntroStep[] {
  return [
    {
      title: "What the colours mean",
      body: `Each hexagon is coloured by two things at once: projected climate exposure in 2050 (redder means more) and present-day wellbeing (bluer means higher). Grey means no data, never zero risk. ${legendWhere(phone)}`,
    },
    {
      title: "Make it yours",
      body: "Pick My priorities to weight what matters to you: jobs, schools, housing cost, heat and more. The map recolours in your browser, and a layer with no data for a place simply drops out of its average.",
    },
    {
      title: "Every number has a source",
      body: `${phone ? "Tap" : "Click"} a hexagon for its values, scores and the datasets behind them, then compare it with another place. Where the data is coarse or missing, the map says so.`,
    },
  ];
}

export const INTRO_STEPS: IntroStep[] = introSteps(false);

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
