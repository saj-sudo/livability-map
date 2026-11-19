// "Share this map" (SPEC §10, §13.50): the words on the share card and the link behind it. The
// card says whose weights these are, what they were and where the data comes from. It never
// lists places. Pure; components/ShareCard.tsx draws it.

import type { ClientSource } from "./clientManifest";
import { shortName, weightable, type DimInfo } from "./dims";
import type { Weights } from "./expressions";
import { presetById } from "../presets";
import { serializeState, type AppState } from "./url";

/** "My map: Early career", or a plain title for hand-set weights. */
export function shareTitle(preset: string | null): string {
  const p = presetById(preset);
  return p ? `A map for: ${p.name}` : "A map for a custom set of priorities";
}

/** "jobs ×3, public transit access ×2, ..." heaviest first, then registry order. */
export function weightsInWords(dims: DimInfo[], weights: Weights): string {
  const rows = dims
    .map((d, i) => ({ d, i, w: weightable(d) ? (weights[d.id] ?? 0) : 0 }))
    .filter((x) => x.w > 0)
    .sort((a, b) => b.w - a.w || a.i - b.i);
  if (!rows.length) return "Nothing is weighted yet.";
  return rows.map(({ d, w }) => `${shortName(d.name).toLowerCase()}${w > 1 ? ` ×${w}` : ""}`).join(", ");
}

/** "Sources: A, B, C and 20 more, listed in full under Methodology." */
export function sourcesLine(sources: Pick<ClientSource, "name">[], named = 3): string {
  if (!sources.length) return "Sources are listed under Methodology.";
  const first = sources.slice(0, named).map((s) => s.name);
  const more = sources.length - first.length;
  return `Sources: ${first.join(", ")}${more > 0 ? ` and ${more} more` : ""}, listed in full under Methodology.`;
}

/** The link "Share this map" copies: the current state plus the flag that shows the card. */
export function shareUrl(state: AppState, origin: string, pathname = "/"): string {
  return `${origin}${pathname}?${serializeState({ ...state, share: true })}`;
}
