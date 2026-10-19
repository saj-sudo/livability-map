"use client";

// Error boundary for every page under the root layout (SPEC §13.40): the header stays, the
// page says plainly what happened and offers a retry. Nothing is reported anywhere
// (invariant 7: no trackers); the error goes to the browser console only.

import { useEffect } from "react";

export default function Error({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main className="mx-auto max-w-xl space-y-3 px-5 py-10 text-[15px] leading-relaxed">
      <h1 className="font-serif text-2xl">Something went wrong on this page</h1>
      <p className="text-muted">The page hit an error it could not recover from by itself. Trying again usually works; if it does not, reloading the page will.</p>
      <div className="flex gap-3">
        <button type="button" onClick={() => retry()} className="rounded-panel border border-rule px-3 py-1.5 hover:bg-rule/60">
          Try again
        </button>
        <a href="/methodology/" className="px-1 py-1.5 text-muted underline hover:text-ink">
          Methodology
        </a>
      </div>
    </main>
  );
}
