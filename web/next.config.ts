import type { NextConfig } from "next";

// SPEC invariant 5: static-first. The site is a static export served by Cloudflare Pages; the
// only runtime requests go to the tiles (R2) and the basemap (OpenFreeMap).
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
