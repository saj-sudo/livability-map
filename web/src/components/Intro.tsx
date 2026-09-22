"use client";

// The three-step first-visit card (SPEC §10). Bottom-centre so the map and the legend stay
// visible while it is read; Escape or Skip closes it; Done marks it seen in localStorage.

import { useEffect, useRef, useState } from "react";
import { dismissIntro, INTRO_STEPS, nextStep } from "../lib/intro";

interface Props {
  onClose: () => void;
}

export default function Intro({ onClose }: Props) {
  const [step, setStep] = useState(0);
  const nextRef = useRef<HTMLButtonElement>(null);
  const s = INTRO_STEPS[step];
  const last = nextStep(step) === null;

  const finish = () => {
    dismissIntro(window.localStorage);
    onClose();
  };

  useEffect(() => {
    nextRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div role="dialog" aria-labelledby="intro-title" aria-describedby="intro-body" className="absolute bottom-6 left-1/2 z-30 w-[24rem] max-w-[calc(100%-1.5rem)] -translate-x-1/2 rounded-panel border border-rule bg-panel-solid p-4 shadow-[0_1px_2px_rgba(0,0,0,.06),0_12px_32px_-12px_rgba(0,0,0,.35)]">
      <div className="flex items-center gap-1.5" aria-hidden="true">
        {INTRO_STEPS.map((_, i) => (
          <span key={i} className={`h-1.5 rounded-full transition-[width,background-color] ${i === step ? "w-5 bg-accent" : "w-1.5 bg-rule"}`} />
        ))}
        <span className="ml-auto text-[11px] text-muted">
          {step + 1} of {INTRO_STEPS.length}
        </span>
      </div>
      <h2 id="intro-title" className="mt-2 font-serif text-[18px] leading-tight">
        {s.title}
      </h2>
      <p id="intro-body" className="mt-1.5 text-[13px] leading-snug">
        {s.body}
      </p>
      <div className="mt-3 flex items-center justify-between">
        <button type="button" onClick={finish} className="rounded-panel px-2 py-1 text-[12px] text-muted hover:bg-rule hover:text-ink">
          Skip
        </button>
        <button
          ref={nextRef}
          type="button"
          onClick={() => {
            const n = nextStep(step);
            if (n === null) finish();
            else setStep(n);
          }}
          className="rounded-panel bg-accent px-3 py-1 text-[13px] text-accent-ink hover:opacity-90"
        >
          {last ? "Start exploring" : "Next"}
        </button>
      </div>
    </div>
  );
}
