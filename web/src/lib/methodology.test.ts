import { describe, expect, it } from "vitest";
import { domainLabel } from "./dims";
import { kindWords, verifiedWords } from "./methodology";

describe("methodology words", () => {
  it("describes each kind of dimension without codes", () => {
    expect(kindWords({ kind: "score", higher_is: "worse", scale: "percentile", group: "hazard" })).toBe("Ranked 0-100 among inhabited places; higher means more exposure");
    expect(kindWords({ kind: "score", higher_is: "better", scale: "percentile", group: "life" })).toBe("Ranked 0-100 among inhabited places; higher is better");
    expect(kindWords({ kind: "score", higher_is: "worse", scale: "percentile", group: "life" })).toMatch(/higher is worse/);
    expect(kindWords({ kind: "score", higher_is: "better", scale: "minmax", group: "wellbeing" })).toMatch(/^Scaled 0-100 within its source/);
    expect(kindWords({ kind: "signed", higher_is: "better", scale: "percentile", group: "life" })).toMatch(/not ranked/);
    expect(kindWords({ kind: "composition", higher_is: "better", scale: "percentile", group: "life" })).toMatch(/context only/);
  });

  it("spells out verification status and scoring domains", () => {
    expect(verifiedWords("search")).toBe("Licence checked by search; first-hand check pending");
    expect(verifiedWords("confirmed")).toMatch(/first-hand/);
    expect(verifiedWords("odd")).toBe("odd");
    expect(domainLabel("us")).toBe("US");
    expect(domainLabel("country:TZ")).toBe("Within country");
    expect(domainLabel("mars")).toBe("mars");
  });
});
