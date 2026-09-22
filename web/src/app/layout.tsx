import type { Metadata } from "next";
import Link from "next/link";
import ThemeToggle from "../components/ThemeToggle";
import { THEME_BOOT_SCRIPT } from "../lib/theme";
import "./globals.css";

export const metadata: Metadata = {
  title: "Livability map",
  description:
    "Projected climate hazard exposure beside present-day wellbeing and the life dimensions you choose, on open data. Shows evidence and gaps; does not recommend where to live.",
};

// SPEC invariant 7: no trackers, no analytics, no accounts. The only script this layout adds
// applies the stored/system theme before first paint (suppressHydrationWarning covers the
// data-theme attribute it sets, which the server cannot know).
// prefetch={false}: a static export does not emit the segment-prefetch payloads Next.js 16 asks for.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
        <header className="flex h-[var(--header-h)] items-center gap-5 border-b border-rule bg-panel-solid px-4">
          <Link href="/" prefetch={false} className="flex shrink-0 items-center gap-2 font-serif text-[19px] font-medium text-ink">
            <HexMark />
            Livability map
          </Link>
          {/* the map page portals its search box here (components/Search.tsx) */}
          <div id="search-slot" className="min-w-0 flex-1" />
          <nav className="flex shrink-0 gap-4 text-[13px] text-muted">
            <Link href="/" prefetch={false} className="hover:text-ink">
              Map
            </Link>
            <Link href="/methodology/" prefetch={false} className="hover:text-ink">
              Methodology
            </Link>
            <Link href="/about/" prefetch={false} className="hover:text-ink">
              About
            </Link>
          </nav>
          {/* the map page portals its "How to read this map" button here */}
          <div id="help-slot" className="shrink-0" />
          <ThemeToggle />
        </header>
        {children}
      </body>
    </html>
  );
}

/** The wordmark's hex: the bivariate corner colours (exposed/struggling and safe/thriving). */
function HexMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 32 32" aria-hidden="true">
      <polygon points="16,2 28,9 28,23 16,30 4,23 4,9" fill="#c85a5a" />
      <polygon points="16,9 22,12.5 22,19.5 16,23 10,19.5 10,12.5" fill="#64acbe" />
    </svg>
  );
}
