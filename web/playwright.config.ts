import { defineConfig } from "@playwright/test";

// e2e smoke test (SPEC §13.40): the fixture build served from out/ with its _headers applied.
// Build first: python -m pipeline --fixtures --res 4 all, then npm run build and
// node scripts/headers.mjs out (CI's e2e job does all three).
const PORT = 3100;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    // headless Chromium has no GPU; SwiftShader gives MapLibre its WebGL 2 context
    launchOptions: { args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"], ...(process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {}) },
  },
  webServer: { command: `node scripts/serve.mjs out ${PORT}`, port: PORT, reuseExistingServer: !process.env.CI },
});
