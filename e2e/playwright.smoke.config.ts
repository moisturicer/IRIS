import { defineConfig, devices } from "@playwright/test";

// IR-904: the smoke tier. A handful of specs against the BUILT frontend with
// every /api request answered by the test itself (smoke/support/mock-api.ts),
// so it needs no database, no worker and no Compose stack and can gate every
// pull request that touches frontend/. The full-stack journeys (playwright.config.ts)
// stay a hand-started run on a pinned build (IR-631); nothing here replaces them.
//
// Unlike the journeys, specs here are independent and the server is a static
// file server, so they run in parallel. Still no retries: a smoke test that
// passes on its second attempt has not passed.

const port = Number(process.env.SMOKE_PORT ?? "4173");

export default defineConfig({
  testDir: "./smoke",
  fullyParallel: true,
  workers: process.env.CI ? 2 : undefined,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 30_000,
  expect: { timeout: 7_500 },
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report-smoke" }],
    ["json", { outputFile: "test-results-smoke/results.json" }],
    // IR-910: the per-screen, per-width table of the viewport matrix.
    ["./smoke/support/matrix-reporter.ts"],
  ],
  outputDir: "test-results-smoke",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    // Trace and video are kept for a failure only: they are the evidence a
    // reviewer opens, and a green run does not need the megabytes.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  // Serves frontend/dist, which the caller builds first (`npm run build` in
  // frontend/). It does not build for you: a stale dist would test the wrong code.
  webServer: {
    command: `npm run preview -- --host 127.0.0.1 --port ${port} --strictPort`,
    cwd: "../frontend",
    url: `http://127.0.0.1:${port}/login`,
    reuseExistingServer: process.env.IRIS_SMOKE_MANAGED_SERVER === "1" || !process.env.CI,
    timeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
