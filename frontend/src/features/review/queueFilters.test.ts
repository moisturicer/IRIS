/**
 * The queue's small rules (IR-143).
 *
 * Run:
 *   npx esbuild src/features/review/queueFilters.test.ts --bundle \
 *     --platform=node --format=esm --define:import.meta.env='{}' | node
 *
 * No test runner is installed (IR-82 covers the backend only), so this uses the
 * same esbuild+node harness as `lib/access.test.ts`. These rules are worth
 * pinning because they are product decisions, not formatting: the escalation
 * thresholds are a claim about when a wait becomes a problem.
 */
import { isQueueFilter, waitLabel, waitTone } from "./queueFilters";

let passed = 0;
let failed = 0;

function ok(name: string, condition: boolean) {
  if (condition) {
    passed += 1;
    console.log(`ok   ${name}`);
  } else {
    failed += 1;
    console.log(`FAIL ${name}`);
  }
}

// --- isQueueFilter ---------------------------------------------------------
// The filter comes from the URL, so it is untrusted input.

ok("the three real filters are accepted",
  isQueueFilter("pending") && isQueueFilter("approved") && isQueueFilter("declined"));

ok("a missing filter is rejected, so the page falls back to Pending",
  !isQueueFilter(null));

ok("an unknown filter is rejected rather than passed to the API",
  !isQueueFilter("rejected") && !isQueueFilter("all") && !isQueueFilter(""));

ok("the check is case-sensitive, matching the endpoint names",
  !isQueueFilter("Pending"));

// --- waitLabel -------------------------------------------------------------

ok("a same-day wait reads as Today, not '0 days'",
  waitLabel(0) === "Today");

ok("a negative wait cannot render as '-1 days' if a clock skews",
  waitLabel(-3) === "Today");

ok("one day is singular",
  waitLabel(1) === "1 day");

ok("more than one day is plural",
  waitLabel(2) === "2 days" && waitLabel(30) === "30 days");

// --- waitTone --------------------------------------------------------------
// Thresholds are inclusive at the boundary: a record that has waited exactly a
// fortnight is already the problem, not one day away from being one.

ok("a fresh wait is unemphasised",
  waitTone(0) === waitTone(6) && waitTone(0).includes("stone"));

ok("a week old escalates to amber",
  waitTone(7).includes("amber") && waitTone(13).includes("amber"));

ok("a fortnight old escalates to red",
  waitTone(14).includes("red") && waitTone(90).includes("red"));

ok("each tone also changes weight, so the signal is not colour alone",
  waitTone(7).includes("font-semibold") && waitTone(14).includes("font-bold"));

console.log(`\n${passed} passed, ${failed} failed`);
// `throw`, not `process.exit` -- this file is typechecked by
// `npm run build` (`tsc && vite build`), and the frontend has no
// @types/node, so `process` is not a name here. An uncaught throw still
// exits non-zero under node, which is what the harness needs. Matches
// lib/access.test.ts, which does the same for the same reason.
if (failed > 0) {
  throw new Error(`${failed} queue-filter test(s) failed`);
}
