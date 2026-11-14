// The place panel's header (SPEC §10): which place this is, in words a person would use. When
// the selection came from search, the searched name leads ("Near Phoenix") and the region the
// hex sits in becomes the subtitle; a click on the map shows the region itself. The area line is
// built directly from numbers, never from the technical "H3 res 4 hex" label.

import { areaLine } from "./format";
import type { HexModel } from "./inspect";
import { foldKey } from "./search";

/** The search result a selection came from, if any. */
export interface PlaceRef {
  name: string;
  kind: "city" | "region";
}

export interface PlaceHeader {
  title: string;
  subtitle: string;
  /** "About 784,000 people in this ~1,770 km² area" */
  line: string;
}

type HeaderModel = Pick<HexModel, "title" | "subtitle" | "populationN" | "areaKm2">;

export function placeHeader(m: HeaderModel, place?: PlaceRef | null): PlaceHeader {
  const line = areaLine(m.populationN, m.areaKm2);
  const region = [m.title, m.subtitle].filter(Boolean).join(", ");
  if (place && place.name.trim()) {
    if (place.kind === "city") return { title: `Near ${place.name}`, subtitle: region, line };
    if (foldKey(place.name) !== foldKey(m.title)) return { title: `In ${place.name}`, subtitle: region, line };
  }
  return { title: m.title, subtitle: m.subtitle, line };
}

/** What a screen reader hears when the panel switches to a new place. */
export function placeAnnouncement(h: Pick<PlaceHeader, "title" | "subtitle">, comparing = false): string {
  const name = [h.title, h.subtitle].filter(Boolean).join(", ");
  return comparing ? `Comparing with ${name}.` : `Showing details for ${name}.`;
}
