// Before any journey: the stack answers, and the seeded accounts exist.
// Records are never seeded here -- each journey creates its own (IR-631 Q11).
import { request } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
import { buildIdentity, manage } from "./stack";

export default async function globalSetup() {
  const base = process.env.E2E_BASE_URL ?? `http://localhost:${process.env.E2E_PORT ?? "8090"}`;
  const ctx = await request.newContext({ baseURL: base, extraHTTPHeaders: { "X-Forwarded-Proto": "https" } });
  const deadline = Date.now() + 180_000;
  let last = "";
  for (;;) {
    try {
      const res = await ctx.get("/api/v1/records/record-types/");
      // 200 or 401 both prove nginx -> gunicorn -> Django is serving.
      if ([200, 401, 403].includes(res.status())) break;
      last = `HTTP ${res.status()}`;
    } catch (err) {
      last = String(err);
    }
    if (Date.now() > deadline) throw new Error(`stack at ${base} not serving: ${last}`);
    await new Promise((r) => setTimeout(r, 3000));
  }
  await ctx.dispose();

  if (!process.env.E2E_SKIP_SEED) {
    // Known-password accounts under production settings, hence --force. The
    // stack is synthetic and private to the run.
    manage("seed_demo", "--accounts-only", "--force");
  }

  // Every party gets a Turnaround, so every turn has a Due date (ADR-043 §2).
  // Institutional data an administrator enters; 5 working days is the value
  // seed_demo uses for demonstrations, not an agreed target. Recorded in
  // build.json so the run record states it.
  const turnaround = Number(process.env.E2E_TURNAROUND_DAYS ?? 5);
  manage("review_clock_for_testing", "--force",
    ...["adviser", "itso", "ierc", "ktto", "rdco"].flatMap((p) => ["--turnaround", `${p}=${turnaround}`]));

  mkdirSync("test-results", { recursive: true });
  writeFileSync("test-results/build.json", JSON.stringify({ ...buildIdentity(), base, turnaround_working_days: Number(process.env.E2E_TURNAROUND_DAYS ?? 5), at: new Date().toISOString() }, null, 2));
}
