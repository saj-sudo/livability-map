"use client";

// Hover readout card (SPEC §10), positioned beside the pointer inside the map shell and
// flipped away from the edges. Pointer-only: touch devices select on tap instead.

import { useLayoutEffect, useRef, useState } from "react";
import type { HoveredHex } from "./MapView";
import type { DimInfo } from "../lib/dims";
import { tooltipModel } from "../lib/tooltip";
import type { AppState } from "../lib/url";

interface Props {
  hover: HoveredHex;
  dims: DimInfo[];
  state: AppState;
}

const GAP = 14;

export default function Tooltip({ hover, dims, state }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: hover.x + GAP, top: hover.y + GAP });
  const m = tooltipModel(hover.props, state.view, dims, state.weights, { pol: state.pol });

  useLayoutEffect(() => {
    const el = ref.current;
    const parent = el?.parentElement;
    if (!el || !parent) return;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const pw = parent.clientWidth;
    const ph = parent.clientHeight;
    const left = hover.x + GAP + w > pw ? Math.max(0, hover.x - GAP - w) : hover.x + GAP;
    const top = hover.y + GAP + h > ph ? Math.max(0, hover.y - GAP - h) : hover.y + GAP;
    setPos({ left, top });
  }, [hover.x, hover.y, m.title, m.line]);

  return (
    <div ref={ref} className="pointer-events-none absolute z-20 max-w-[16rem] rounded-panel border border-rule bg-panel-solid px-2.5 py-1.5 shadow-[0_4px_14px_-6px_rgba(0,0,0,.35)]" style={{ left: pos.left, top: pos.top }} aria-hidden="true">
      <div className={`text-[13px] leading-tight ${m.slim ? "text-muted" : "font-serif text-[14px]"}`}>{m.title}</div>
      {m.subtitle && <div className="text-[11px] text-muted">{m.subtitle}</div>}
      <div className="mt-0.5 text-[12px]">{m.line}</div>
    </div>
  );
}
