import { describe, expect, it } from "vitest";
import type { DimInfo } from "./dims";
import { plateTitle } from "./plate";
import { VIEWS } from "./url";

const dim = (id: string, name: string, group: DimInfo["group"], scale: DimInfo["scale"] = "percentile"): DimInfo => ({ id, name, group, kind: "score", higher_is: "worse", chip: "", note: "", scale, available: true });
const DIMS = [dim("heat", "Extreme heat (days > 35C)", "hazard"), dim("humid", "Humid heat", "hazard"), dim("rflood", "Riverine flood", "hazard"), dim("cflood", "Coastal flood", "hazard"), dim("wstress", "Water stress", "hazard"), dim("wb", "Wellbeing", "wellbeing", "minmax")];
const M = { scenario: "rcp45_ssp245", horizon: "2050" };

describe("plate title (SPEC §10: scenario and horizon always on screen)", () => {
  it("names the year and the pathway on every projected view", () => {
    for (const view of VIEWS.filter((v) => v !== "wb")) {
      const p = plateTitle(view, DIMS, M);
      expect(`${p.title} ${p.sub}`, view).toMatch(/2050/);
      expect(p.sub, view).toMatch(/RCP4\.5 \/ SSP2-4\.5/);
    }
  });

  it("titles the default as one variable and says heat counts twice", () => {
    const p = plateTitle("exp", DIMS, M);
    expect(p.title).toBe("Climate exposure, 2050");
    expect(p.sub).toMatch(/heat counted twice/);
  });

  it("titles a hazard by its short name, wellbeing as present-day, and the fit by its preset", () => {
    expect(plateTitle("heat", DIMS, M).title).toBe("Extreme heat, 2050");
    expect(plateTitle("wb", DIMS, M)).toEqual({ title: "Wellbeing today", sub: "Present-day; a score within its source." });
    expect(plateTitle("priorities", DIMS, M, "Early career").title).toBe("Fit with Early career");
    expect(plateTitle("priorities", DIMS, M).title).toBe("Fit with your priorities");
    expect(plateTitle("priorities", DIMS, M).sub).toMatch(/Not a ranking/);
    expect(plateTitle("bivar", DIMS, M).sub).toMatch(/only where the figure is regional or finer/);
  });
});
