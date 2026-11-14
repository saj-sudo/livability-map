import { describe, expect, it } from "vitest";
import { diffOutlines, EMPTY_SELECTION, selectedIds, selectionReducer, type Selection, type SelectionAction } from "./selection";

type H = { h3: string };
const A = { h3: "a" };
const B = { h3: "b" };
const C = { h3: "c" };
const run = (s: Selection<H>, ...actions: SelectionAction<H>[]) => actions.reduce(selectionReducer<H>, s);
const empty: Selection<H> = EMPTY_SELECTION;

describe("selection and compare state", () => {
  it("selects on click and clears on an empty click", () => {
    expect(run(empty, { type: "select", hex: A })).toEqual({ a: A, b: null, picking: false });
    expect(run(empty, { type: "select", hex: A }, { type: "select", hex: null })).toEqual(empty);
  });

  it("picks a second place without losing the first", () => {
    let s = run(empty, { type: "select", hex: A }, { type: "startPicking" });
    expect(s.picking).toBe(true);
    s = run(s, { type: "select", hex: null }); // the sea: nothing happens to A
    expect(s).toEqual({ a: A, b: null, picking: true });
    s = run(s, { type: "select", hex: A }); // A itself is not B
    expect(s.picking).toBe(true);
    s = run(s, { type: "select", hex: B });
    expect(s).toEqual({ a: A, b: B, picking: false });
    expect(selectedIds(s)).toEqual(["a", "b"]);
  });

  it("cannot start picking with nothing selected", () => {
    expect(run(empty, { type: "startPicking" })).toBe(empty);
  });

  it("cancels picking, swaps and closes the comparison", () => {
    const s = run(empty, { type: "select", hex: A }, { type: "startPicking" }, { type: "cancelPicking" });
    expect(s).toEqual({ a: A, b: null, picking: false });
    const both = run(s, { type: "startPicking" }, { type: "select", hex: B });
    expect(run(both, { type: "swap" })).toEqual({ a: B, b: A, picking: false });
    expect(run(both, { type: "closeCompare" })).toEqual({ a: A, b: null, picking: false });
    expect(run(both, { type: "close" })).toEqual(empty);
    expect(selectedIds(run(both, { type: "close" }))).toEqual([]);
  });

  it("re-picks B and replaces A on a later click", () => {
    const both = run(empty, { type: "select", hex: A }, { type: "startPicking" }, { type: "select", hex: B });
    expect(run(both, { type: "startPicking" }, { type: "select", hex: C })).toEqual({ a: A, b: C, picking: false });
    expect(run(both, { type: "select", hex: C })).toEqual({ a: C, b: B, picking: false });
    expect(run(both, { type: "select", hex: B })).toEqual({ a: B, b: null, picking: false }); // never A = B
  });

  it("Escape closes the innermost thing first", () => {
    const picking = run(empty, { type: "select", hex: A }, { type: "startPicking" });
    expect(run(picking, { type: "escape" })).toEqual({ a: A, b: null, picking: false });
    const both = run(picking, { type: "select", hex: B });
    expect(run(both, { type: "escape" })).toEqual({ a: A, b: null, picking: false });
    expect(run(both, { type: "escape" }, { type: "escape" })).toEqual(empty);
    expect(run(empty, { type: "escape" })).toBe(empty);
  });
});

describe("outline sync", () => {
  const k = (id: string, sourceLayer = "hex4", source = "hexes") => ({ source, sourceLayer, id });
  it("clears what is no longer selected and sets only what is new", () => {
    expect(diffOutlines([], [k("a")])).toEqual({ clear: [], set: [k("a")] });
    expect(diffOutlines([k("a")], [k("a"), k("b")])).toEqual({ clear: [], set: [k("b")] });
    expect(diffOutlines([k("a"), k("b")], [k("b")])).toEqual({ clear: [k("a")], set: [] });
    expect(diffOutlines([k("a")], [])).toEqual({ clear: [k("a")], set: [] });
  });

  it("treats the same id in another layer or archive as a different outline", () => {
    expect(diffOutlines([k("a", "hex4")], [k("a", "hex5")])).toEqual({ clear: [k("a", "hex4")], set: [k("a", "hex5")] });
    expect(diffOutlines([k("a", "hex6", "hexes_nbhd")], [k("a", "hex6", "hexes")]).clear).toHaveLength(1);
  });
});
