import { defineConfig, devices } from "@playwright/test";

// IR-631: one pinned build, one browser, one journey at a time.
//
// Serial (workers: 1, fullyParallel: false) because every journey shares one
// database, one set of Celery workers and one Mailpit inbox; in parallel their
// side effects interleave and a failure stops meaning anything. Deliberate
// concurrency lives in specs/integrity, where it is what is being tested, and
// is made with simultaneous API requests rather than parallel workers.
//
// No retries: a journey that passes on its second attempt has not passed. A
// flake is recorded as a failure with its trace, per the run record's rules.

const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${process.env.E2E_PORT ?? "8090"}`;

export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  globalSetup: "./support/global-setup.ts",
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],
  use: {
    baseURL,
    // TLS ends in a proxy in front of nginx in production, and production
    // settings redirect any request not marked as HTTPS. Nothing in this
    // repository terminates TLS (IR-662), and TLS is out of IR-631's scope,
    // so the run sends the header that proxy would. nginx passes only
    // "https" through (frontend/nginx.conf). Recorded as a limitation.
    extraHTTPHeaders: { "X-Forwarded-Proto": "https" },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
