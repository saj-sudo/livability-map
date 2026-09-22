import { describe, expect, it } from "vitest";
import { DEFAULT_STATE, parseState, serializeState, type AppState } from "./url";

describe("url state", () => {
  it("round-trips a full priorities state", () => {
    const s: AppState = { lat: 33.45, lng: -112.07, z: 6.25, view: "priorities", preset: null, weights: { jobs: 3, heat: 1, race: 2 }, pol: "left", race: "b", conf: false, inh: true };
    const back = parseState(serializeState(s));
    expect(back.view).toBe("priorities");
    expect(back.weights).toEqual({ jobs: 3, heat: 1, race: 2 });
    expect(back.pol).toBe("left");
    expect(back.race).toBe("b");
    expect(back.conf).toBe(false);
    expect(back.inh).toBe(true);
    expect(back.lat).toBeCloseTo(33.45, 3);
    expect(back.lng).toBeCloseTo(-112.07, 3);
    expect(back.z).toBeCloseTo(6.25, 2);
  });

  it("omits defaults and uses a preset name instead of weights", () => {
    const s: AppState = { ...DEFAULT_STATE, view: "priorities", preset: "queer", pol: "left" };
    const q = serializeState(s);
    expect(q).toContain("preset=queer");
    expect(q).not.toContain("&w=");
    expect(q).not.toContain("conf=");
    expect(q).not.toContain("pol="); // the preset's own pick is implied
    const back = parseState(q);
    expect(back.preset).toBe("queer");
    expect(back.weights.lgbtq).toBe(3);
    expect(back.pol).toBe("left"); // the preset's pick
  });

  it("falls back to defaults on garbage", () => {
    const back = parseState("?lat=abc&z=99&view=nope&preset=zzz&pol=up&w=x,9,-1&inh=maybe");
    expect(back.lat).toBe(DEFAULT_STATE.lat);
    expect(back.z).toBe(14); // clamped
    expect(back.view).toBe("bivar");
    expect(back.preset).toBeNull();
    expect(back.weights).toEqual({ rflood: 5 }); // second slot is rflood, clamped to 5
    expect(back.pol).toBe("competitive");
    expect(back.inh).toBe(false);
  });

  it("weights in the URL override a preset", () => {
    const back = parseState("view=priorities&preset=climate&w=0,0,0,0,2");
    expect(back.preset).toBeNull();
    expect(back.weights).toEqual({ wb: 2 });
  });
});
