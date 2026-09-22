// MapLibre style expressions (SPEC §9.3, §20.5). Pure functions so they can be unit-tested with
// the style-spec's createExpression. Every `get` of a possibly-missing attribute is guarded with
// `has`/`coalesce`: an arithmetic on null throws at evaluation time and the whole paint
// property silently falls back to its default. Colours come from the palette of the current
// theme (PALETTES.light when none is given).

import type { ExpressionSpecification, FilterSpecification } from "maplibre-gl";
import type { DimInfo } from "./dims";
import { PALETTES, type Palette } from "./palette";
import type { PolPick, RacePick } from "../presets";

export type Expr = ExpressionSpecification;

/** Default bivariate view: classes 1-9, class 0 / missing grey (§8.4, §9.3). */
export function bivarColor(pal: Palette = PALETTES.light): Expr {
  const stops: (number | string)[] = [];
  for (let k = 1; k <= 9; k++) stops.push(k, pal.bivar[k]);
  return ["match", ["coalesce", ["get", "bivar"], 0], ...stops, pal.grey] as unknown as Expr;
}

/** A hazard or dimension has data on a hex exactly when its score attribute is present
 *  (the tiler drops attributes for missing values, invariant 3); the flags are checked too. */
export function missingExpr(id: string): Expr {
  return [
    "any",
    ["!", ["has", `${id}_score`]],
    ["==", ["coalesce", ["get", `${id}_ok`], true], false],
    ["==", ["coalesce", ["get", `${id}_res`], "x"], "none"],
  ] as unknown as Expr;
}

/** Sequential ramp on {id}_score; grey when the hex has no data. */
export function scoreColor(id: string, ramp: string[], grey: string = PALETTES.light.grey): Expr {
  return ["case", missingExpr(id), grey, ["interpolate", ["linear"], ["get", `${id}_score`], 0, ramp[0], 50, ramp[1], 100, ramp[2]]] as unknown as Expr;
}

export function rampFor(dim: DimInfo, pal: Palette = PALETTES.light): string[] {
  if (dim.group === "hazard") return pal.rampHazard;
  if (dim.group === "wellbeing") return pal.rampWellbeing;
  // present-day environment: "more is worse" layers (PM2.5, fire, drought) read like hazards
  if (dim.group === "env" && dim.higher_is === "worse") return pal.rampHazard;
  return pal.rampGood;
}

export const inhabitedFilter = (showUninhabited: boolean): FilterSpecification =>
  (showUninhabited ? ["boolean", true] : ["==", ["get", "inhabited"], true]) as unknown as FilterSpecification;

/** Reduced-confidence hatch: fewer than four hazard layers (§9.3, decision §13.4). */
export const hatchFilter = (): FilterSpecification => ["<", ["coalesce", ["get", "coverage"], 0], 4] as unknown as FilterSpecification;

/** National-fallback wellbeing gets a dashed outline (§9.3). */
export const nationalFilter = (): FilterSpecification => ["==", ["coalesce", ["get", "wb_res"], "none"], "national"] as unknown as FilterSpecification;

export interface Picks {
  pol: PolPick;
  race: RacePick;
}

export type Weights = Record<string, number>;

/** The attribute whose presence means "this hex has the dimension". */
export function hasAttr(d: DimInfo): string {
  return d.kind === "score" ? `${d.id}_score` : d.kind === "signed" ? `${d.id}_lean` : `${d.id}_w`;
}

export function hasExpr(d: DimInfo): Expr {
  return ["has", hasAttr(d)] as unknown as Expr;
}

/** 0..100 "how well this hex matches what the person wants" (§20.5). */
export function matchExpr(d: DimInfo, p: Picks): Expr {
  if (d.kind === "score") {
    const score: Expr = ["get", `${d.id}_score`] as unknown as Expr;
    return (d.higher_is === "worse" ? ["-", 100, score] : score) as unknown as Expr;
  }
  if (d.kind === "signed") {
    const lean: Expr = ["get", `${d.id}_lean`] as unknown as Expr; // -100 (R) .. +100 (D)
    if (p.pol === "left") return ["/", ["+", lean, 100], 2] as unknown as Expr;
    if (p.pol === "right") return ["/", ["-", 100, lean], 2] as unknown as Expr;
    return ["-", 100, ["abs", lean]] as unknown as Expr; // competitive: closer to even is better
  }
  if (p.race !== "diverse") return ["get", `${d.id}_${p.race}`] as unknown as Expr; // percent share
  // diverse: 100 minus the largest share (100 when no group dominates, 0 when one group is everyone)
  return ["-", 100, ["max", ["get", `${d.id}_w`], ["get", `${d.id}_b`], ["get", `${d.id}_h`], ["get", `${d.id}_a`], ["get", `${d.id}_o`]]] as unknown as Expr;
}

/** sum(w_i * match_i * has_i) / sum(w_i * has_i); -1 when no weighted dimension has data. */
export function compositeExpression(dims: DimInfo[], weights: Weights, p: Picks): Expr {
  const active = dims.filter((d) => (weights[d.id] ?? 0) > 0);
  if (!active.length) return -1 as unknown as Expr;
  const num: unknown[] = ["+", 0];
  const den: unknown[] = ["+", 0];
  for (const d of active) {
    const w = weights[d.id];
    num.push(["case", hasExpr(d), ["*", w, matchExpr(d, p)], 0]);
    den.push(["case", hasExpr(d), w, 0]);
  }
  return ["let", "num", num, "den", den, ["case", ["<=", ["var", "den"], 0], -1, ["/", ["var", "num"], ["var", "den"]]]] as unknown as Expr;
}

export function priorityColor(dims: DimInfo[], weights: Weights, p: Picks, pal: Palette = PALETTES.light): Expr {
  const r = pal.rampPriority;
  return ["let", "c", compositeExpression(dims, weights, p), ["case", ["<", ["var", "c"], 0], pal.grey, ["interpolate", ["linear"], ["var", "c"], 0, r[0], 50, r[1], 100, r[2]]]] as unknown as Expr;
}
