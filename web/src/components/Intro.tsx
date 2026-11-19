"use client";

// The first-visit card (SPEC §10, §13.50): one question, two doors. Either door sets the view
// and marks the card seen in localStorage; Escape or Skip closes it without changing the view.

import { useEffect, useRef } from "react";
import { dismissIntro, INTRO_DOORS, INTRO_FINE, INTRO_TITLE } from "../lib/intro";
import type { ViewId } from "../lib/url";

interface Props {
  onClose: () => void;
  /** a door was chosen: open that view */
  onDoor: (view: ViewId) => void;
}

export default function Intro({ onClose, onDoor }: Props) {
  const first = useRef<HTMLButtonElement>(null);

  const finish = () => {
    dismissIntro(window.localStorage);
    onClose();
  };

  useEffect(() => {
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      // Escape while typing (the search box) belongs to that field, not to the intro
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div role="dialog" aria-labelledby="intro-title" aria-describedby="intro-fine" className="absolute bottom-5 left-1/2 z-30 flex w-[24rem] max-w-[calc(100%-1.5rem)] -translate-x-1/2 flex-col gap-2.5 rounded-panel border border-rule bg-panel-solid p-4">
      <h2 id="intro-title" className="font-serif text-[21px] leading-tight">
        {INTRO_TITLE}
      </h2>
      {INTRO_DOORS.map((d, i) => (
        <button
          key={d.view}
          ref={i === 0 ? first : undefined}
          type="button"
          onClick={() => {
            onDoor(d.view);
            finish();
          }}
          className={`flex min-h-16 flex-col justify-center gap-0.5 rounded-panel border border-ink px-3.5 py-2.5 text-left ${i === 0 ? "bg-ink text-panel-solid" : "hover:bg-rule/50"}`}
        >
          <span className="font-serif text-[18px] leading-tight">{d.title}</span>
          <span className={`text-small leading-snug ${i === 0 ? "opacity-85" : "text-muted"}`}>{d.body}</span>
        </button>
      ))}
      <p id="intro-fine" className="text-small leading-snug text-muted">
        {INTRO_FINE}
      </p>
      <button type="button" onClick={finish} className="-mb-1 flex min-h-[44px] items-center self-start rounded-panel px-2 text-small text-muted hover:bg-rule hover:text-ink">
        Skip
      </button>
    </div>
  );
}
