import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "livability-map",
  description:
    "Projected climate hazard exposure beside present-day wellbeing and the life dimensions you choose, on open data. Shows evidence and gaps; does not recommend where to live.",
};

// SPEC invariant 7: no trackers, no analytics, no accounts. This layout adds nothing but markup.
// prefetch={false}: a static export does not emit the segment-prefetch payloads Next.js 16 asks for.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="flex h-12 items-center gap-6 border-b border-[var(--border)] bg-white px-4 text-sm">
          <Link href="/" prefetch={false} className="font-semibold tracking-tight">
            livability-map
          </Link>
          <nav className="flex gap-4 text-[var(--muted)]">
            <Link href="/" prefetch={false}>Map</Link>
            <Link href="/methodology/" prefetch={false}>Methodology</Link>
            <Link href="/about/" prefetch={false}>About</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
