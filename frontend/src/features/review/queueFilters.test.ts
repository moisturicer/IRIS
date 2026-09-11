/**
 * The queue's small rules (IR-143).
 *
 * Runs under vitest: `npm test` from `frontend/` (IR-210). This file predates
 * the runner and was executed by a hand-written esbuild-plus-node incantation;
 * its assertions are unchanged, only the harness around them is now real.
 *
 * These rules are worth pinning because they are product decisions, not
 * formatting: the escalation thresholds are a claim about when a wait becomes
 * a problem.
 */
import { isQueueFilter, waitLabel, waitTone } from "./queueFilters";

import { expect, test } from "vitest";

/**
 * Kept as `ok(name, condition)` rather than rewritten into `expect` at every
 * call site: the assertions below read as a table of product decisions, and
 * reshaping them would bury the diff that converted this file to a real runner
 * (IR-210). The failure message now comes from vitest.
 */
function ok(name: string, condition: boolean) {
  test(name, () => {
    expect(condition).toBe(true);
  });
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
