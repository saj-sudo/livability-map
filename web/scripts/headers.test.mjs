import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { headersFile, inlineScriptHashes, pageCsp, pagePath } from "./headers.mjs";

const sha = (s) => `'sha256-${createHash("sha256").update(s, "utf8").digest("base64")}'`;

describe("_headers (SPEC §13.40)", () => {
  it("hashes inline scripts only", () => {
    const html = `<script>a()</script><script src="/x.js"></script><script id="t">b()</script><script></script><script>a()</script>`;
    expect(inlineScriptHashes(html)).toEqual([sha("a()"), sha("b()")]);
  });

  it("allows only the page's own scripts and the map's origins", () => {
    const csp = pageCsp({ scriptHashes: [sha("a()")], dataOrigin: "https://tiles.example.org" });
    expect(csp).toContain(`script-src 'self' ${sha("a()")}`);
    expect(csp).not.toMatch(/script-src[^;]*unsafe-inline/);
    expect(csp).toContain("connect-src 'self' https://tiles.example.org https://tiles.openfreemap.org");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(pageCsp({ scriptHashes: [] })).toContain("connect-src 'self' https://tiles.openfreemap.org");
  });

  it("maps export files to served paths", () => {
    expect(pagePath("index.html")).toBe("/");
    expect(pagePath("about/index.html")).toBe("/about/");
    expect(pagePath("404.html")).toBe("/404.html");
  });

  it("writes common headers once and a CSP per page", () => {
    const f = headersFile([{ path: "/about/", hashes: [sha("x")] }, { path: "/", hashes: [] }], "https://t.example");
    expect(f.split("\n")[0]).toBe("/*");
    expect(f).toContain("X-Content-Type-Options: nosniff");
    expect(f).toContain("/_next/static/*\n  Cache-Control: public, max-age=31536000, immutable");
    expect(f.indexOf("\n/\n")).toBeLessThan(f.indexOf("\n/about/\n"));
    expect(f.match(/Content-Security-Policy/g)).toHaveLength(2);
    expect(f.split("\n").every((l) => l.length <= 2000)).toBe(true); // Pages' per-line limit
  });
});
