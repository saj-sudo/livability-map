import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { shareTitle, shareUrl, sourcesLine, weightsInWords } from "./share";
import { DEFAULT_STATE, parseState } from "./url";

const dim = (id: string, name: string, kind: DimInfo["kind"] = "score"): DimInfo => ({ id, name, group: "life", kind, higher_is: "better", chip: "", note: "", scale: "percentile", available: true });
const DIMS = [dim("heat", "Extreme heat (days > 35C)"), dim("jobs", "Early-career job market"), dim("transit", "Public transit access"), dim("race", "Racial and ethnic composition", "composition")];

describe("share card (SPEC §10, §13.50)", () => {
  it("titles the card by the preset, or says the weights are custom", () => {
    expect(shareTitle("early")).toBe("A map for: Early career");
    expect(shareTitle(null)).toBe("A map for a custom set of priorities");
    expect(shareTitle("nope")).toBe("A map for a custom set of priorities");
  });

  it("puts the weights in words, heaviest first, and never a composition dimension", () => {
    expect(weightsInWords(DIMS, { heat: 1, jobs: 3, transit: 2, race: 5 })).toBe("early-career job market ×3, public transit access ×2, extreme heat");
    expect(weightsInWords(DIMS, {})).toBe("Nothing is weighted yet.");
  });

  it("names a few sources and counts the rest", () => {
    const s = ["A", "B", "C", "D", "E"].map((name) => ({ name }));
    expect(sourcesLine(s)).toBe("Sources: A, B, C and 2 more, listed in full under Methodology.");
    expect(sourcesLine(s.slice(0, 2))).toBe("Sources: A, B, listed in full under Methodology.");
    expect(sourcesLine([])).toMatch(/Methodology/);
  });

  it("builds a link that reopens the same map with the card, and nothing about places beyond the view position", () => {
    const state = { ...DEFAULT_STATE, view: "priorities" as const, preset: "early", weights: { jobs: 3 } };
    const url = shareUrl(state, "https://example.org");
    expect(url).toMatch(/^https:\/\/example\.org\/\?/);
    const back = parseState(url.split("?")[1]);
    expect(back.share).toBe(true);
    expect(back.view).toBe("priorities");
    expect(back.preset).toBe("early");
  });
});
