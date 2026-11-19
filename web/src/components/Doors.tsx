"use client";

// The two doors (SPEC §10, §13.50): "Climate in 2050" and "What matters to you". One switch at the
// top of the rail and in the phone sheet's peek, so the second door is one tap from the first view.

import type { ViewId } from "../lib/url";

export const DOOR_LABELS = { climate: "Climate in 2050", priorities: "What matters to you" } as const;

interface Props {
  view: ViewId;
  /** the view each door opens; staying inside the climate door keeps the current layer */
  onDoor: (view: ViewId) => void;
}

export default function Doors({ view, onDoor }: Props) {
  const inPriorities = view === "priorities";
  const cls = (on: boolean) => `grid min-h-[44px] place-items-center px-2 py-1 text-center text-small leading-tight ${on ? "bg-ink font-semibold text-panel-solid" : "text-ink hover:bg-rule/50"}`;
  return (
    <div className="grid grid-cols-2 overflow-hidden rounded-panel border border-ink" role="group" aria-label="What the map shows">
      <button type="button" aria-pressed={!inPriorities} className={cls(!inPriorities)} onClick={() => inPriorities && onDoor("exp")}>
        {DOOR_LABELS.climate}
      </button>
      <button type="button" aria-pressed={inPriorities} className={`${cls(inPriorities)} border-l border-ink`} onClick={() => !inPriorities && onDoor("priorities")}>
        {DOOR_LABELS.priorities}
      </button>
    </div>
  );
}
