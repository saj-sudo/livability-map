"use client";

// Last-resort boundary for errors in the root layout itself (SPEC §13.40). It replaces the
// whole document, so it carries its own minimal styling; nothing is reported (invariant 7).

export default function GlobalError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", maxWidth: "36rem", margin: "3rem auto", padding: "0 1.25rem", lineHeight: 1.5 }}>
        <title>Livability map: something went wrong</title>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 500 }}>Something went wrong</h1>
        <p>The page could not load. Trying again usually works; if it does not, reload the page.</p>
        <button type="button" onClick={() => retry()} style={{ padding: "0.4rem 0.8rem" }}>
          Try again
        </button>
      </body>
    </html>
  );
}
