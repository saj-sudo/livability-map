"use client";

// Phone layout (SPEC §10): the panels live in one bottom sheet with a drag handle and tabs.
// Three snaps (peek / half / full); pointer events on the handle drive the drag, CSS
// transforms do the motion (transitions are cut by the global reduced-motion rule).

import { useEffect, useRef, useState } from "react";
import { nextSnap, snapHeight, SNAP_FRACTIONS, type Snap } from "../lib/sheet";

export interface SheetTab {
  id: string;
  label: string;
}

interface Props {
  snap: Snap;
  onSnap: (s: Snap) => void;
  tabs: SheetTab[];
  tab: string;
  onTab: (id: string) => void;
  children: React.ReactNode;
}

export default function Sheet({ snap, onSnap, tabs, tab, onTab, children }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const [containerH, setContainerH] = useState(0);
  const [dragDy, setDragDy] = useState<number | null>(null);
  const drag = useRef<{ y0: number; t0: number; yLast: number; tLast: number } | null>(null);

  // the sheet is sized against its parent (the map shell), which follows the dynamic viewport
  useEffect(() => {
    const el = root.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(() => setContainerH(el.clientHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const fullH = containerH * SNAP_FRACTIONS.full;
  const visible = containerH ? snapHeight(snap, containerH) - (dragDy ?? 0) : 0;
  const clamped = Math.max(snapHeight("peek", containerH), Math.min(fullH, visible));
  const translate = containerH ? fullH - clamped : 0;

  const onPointerDown = (e: React.PointerEvent) => {
    drag.current = { y0: e.clientY, t0: e.timeStamp, yLast: e.clientY, tLast: e.timeStamp };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setDragDy(0);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    drag.current.yLast = e.clientY;
    drag.current.tLast = e.timeStamp;
    setDragDy(e.clientY - drag.current.y0);
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    setDragDy(null);
    if (!d || !containerH) return;
    const dy = e.clientY - d.y0;
    const dt = Math.max(1, e.timeStamp - d.t0);
    const v = dy / dt; // px/ms, positive = down
    if (Math.abs(dy) < 4) {
      onSnap(snap === "peek" ? "half" : snap === "half" ? "full" : "peek"); // a tap cycles
      return;
    }
    onSnap(nextSnap(snap, dy, v, containerH));
  };

  return (
    <div
      ref={root}
      className="absolute inset-x-0 bottom-0 z-20 flex flex-col rounded-t-[10px] border border-b-0 border-rule bg-panel-solid shadow-[0_-8px_24px_-12px_rgba(0,0,0,.35)]"
      style={{ height: fullH || undefined, transform: `translateY(${translate}px)`, transition: dragDy === null ? "transform 220ms cubic-bezier(.2,.8,.2,1)" : "none", paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
      role="region"
      aria-label="Map panels"
    >
      <div className="touch-none select-none px-3 pb-1 pt-2" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}>
        <button
          type="button"
          className="mx-auto block h-1.5 w-10 rounded-full bg-rule"
          aria-label={snap === "full" ? "Collapse panels" : "Expand panels"}
          // keyboard and switch access (detail 0); a pointer tap is already handled by the drag
          // handlers on the parent, so it must not cycle twice
          onClick={(e) => {
            if (e.detail === 0) onSnap(snap === "peek" ? "half" : snap === "half" ? "full" : "peek");
          }}
        />
        <div className="mt-2 flex gap-1" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={t.id === tab}
              onClick={() => {
                onTab(t.id);
                if (snap === "peek") onSnap("half");
              }}
              className={`rounded-full px-3 py-1 text-[13px] ${t.id === tab ? "bg-rule font-medium text-ink" : "text-muted"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-3 pb-3" role="tabpanel">
        {children}
      </div>
    </div>
  );
}
