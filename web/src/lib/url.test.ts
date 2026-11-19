import { describe, expect, it } from "vitest";
import { MAP_MAX_ZOOM, MAP_MIN_ZOOM } from "./config";
import { DEFAULT_STATE, parseState, serializeState, VIEWS, type AppState } from "./url";

describe("url state", () => {
  it("round-trips a full priorities state", () => {
    const s: AppState = { lat: 33.45, lng: -112.07, z: 6.25, view: "priorities", preset: null, weights: { jobs: 3, heat: 1 }, pol: "left", conf: false, inh: true };
    const back = parseState(serializeState(s));
    expect(back.view).toBe("priorities");
    expect(back.weights).toEqual({ jobs: 3, heat: 1 });
    expect(back.pol).toBe("left");
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
    expect(q).toContain("view=priorities");
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
    expect(back.view).toBe("exp"); // an unknown view= is not an old link: today's default
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

  it("ignores a race weight and pick from links made before §13.40", () => {
    // w= slots: heat, rflood, cflood, wstress, wb, jobs, transit, school, lgbtq, pol, race
    const old = parseState("?view=priorities&w=0,0,0,0,0,2,0,0,0,0,4&race=b");
    expect(old.weights).toEqual({ jobs: 2 });
    expect("race" in old).toBe(false);
    expect(serializeState({ ...DEFAULT_STATE, view: "priorities", weights: { jobs: 2, race: 4 } })).not.toMatch(/race|,4/);
  });

  it("keeps weights, preset and the political pick in every view, not only My priorities", () => {
    const s: AppState = { ...DEFAULT_STATE, view: "heat", weights: { jobs: 3, pol: 2 }, pol: "right" };
    const back = parseState(serializeState(s));
    expect(back.view).toBe("heat");
    expect(parseState("?view=humid").view).toBe("humid"); // the humid-heat layer is a view of its own (§13.47)
    // humid takes the slot after industry, so a link written before it keeps every earlier weight
    const humid = parseState(serializeState({ ...DEFAULT_STATE, view: "priorities", weights: { heat: 2, humid: 2 } }));
    expect(humid.weights).toEqual({ heat: 2, humid: 2 });
    expect(back.weights).toEqual({ jobs: 3, pol: 2 });
    expect(back.pol).toBe("right");
    const preset = parseState(serializeState({ ...DEFAULT_STATE, view: "bivar", preset: "queer", weights: { lgbtq: 3 } }));
    expect(preset.view).toBe("bivar");
    expect(preset.preset).toBe("queer");
    expect(preset.weights.lgbtq).toBe(3);
  });

  it("clamps the zoom to the map's own limits", () => {
    expect(parseState("?z=0").z).toBe(MAP_MIN_ZOOM);
    expect(parseState("?z=1.5").z).toBe(MAP_MIN_ZOOM);
    expect(parseState("?z=40").z).toBe(MAP_MAX_ZOOM);
    expect(parseState("?z=5.5").z).toBe(5.5);
  });

  it("keeps old links meaning what they meant: rule B (SPEC §13.50)", () => {
    // written before the redesign: a position, no view= (bivariate was the default and was omitted)
    expect(parseState("?lat=42.500&lng=13.000&z=6.00").view).toBe("bivar");
    expect(parseState("?lat=42.5&lng=13&z=6&preset=early").view).toBe("bivar");
    // a bare address is a first visit: today's default, one variable
    expect(parseState("").view).toBe("exp");
    expect(DEFAULT_STATE.view).toBe("exp");
    // view= always wins, and is always written from now on
    expect(parseState("?lat=1&lng=2&z=3&view=exp").view).toBe("exp");
    expect(parseState("?view=wb").view).toBe("wb");
    expect(serializeState(DEFAULT_STATE)).toContain("view=exp");
    expect(serializeState({ ...DEFAULT_STATE, view: "bivar" })).toContain("view=bivar");
    expect(parseState(serializeState(DEFAULT_STATE)).view).toBe("exp");
  });

  it("appends new view ids, never reorders them", () => {
    expect(VIEWS.slice(0, 8)).toEqual(["bivar", "heat", "humid", "rflood", "cflood", "wstress", "wb", "priorities"]);
    expect(VIEWS[8]).toBe("exp");
  });

  it("carries the share flag only when set", () => {
    expect(parseState("?view=priorities&preset=early&share=1").share).toBe(true);
    expect("share" in parseState("?view=priorities&preset=early")).toBe(false);
    expect(serializeState({ ...DEFAULT_STATE, share: true })).toContain("share=1");
    expect(serializeState(DEFAULT_STATE)).not.toContain("share");
  });
});
