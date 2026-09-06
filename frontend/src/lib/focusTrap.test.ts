/**
 * Tests for the modal focus-trap seam (IR-158).
 *
 * There is no test runner in this repo yet (IR-82 / IR-163). Run these today with:
 *
 *   docker exec iris-frontend-1 sh -c "cd /app && \
 *     ./node_modules/.bin/esbuild src/lib/focusTrap.test.ts \
 *       --bundle --platform=node --format=esm --outfile=/tmp/t.mjs && node /tmp/t.mjs"
 *
 * Or, without the container, from `frontend/`:
 *
 *   ./node_modules/.bin/esbuild src/lib/focusTrap.test.ts \
 *     --bundle --platform=node --format=esm --outfile=.tmp-focustrap.mjs && \
 *     node .tmp-focustrap.mjs
 *
 * Same conventions as `tokenRefresh.test.ts`: hand-rolled assertions rather than
 * `node:assert`, because `npm run build` runs `tsc` across `src/` and there is no
 * `@types/node`. When a runner lands, each `test(...)` becomes an `it(...)`.
 *
 * Why this deserves a test: `Modal` gates two irreversible actions -- reject
 * confirmation and role approval -- that a keyboard user currently cannot stay
 * inside, because Tab escapes to the page behind the dialog. The wrap-around
 * arithmetic (and the "focus already escaped" recovery) is the part that is easy
 * to get subtly wrong and impossible to see in a screenshot, so it is pulled out
 * of the component and tested directly. `nextTrapFocus` is generic over the
 * element type precisely so it can be exercised here with plain strings, with no
 * jsdom and no DOM types.
 */

import { nextTrapFocus } from "./focusTrap";

// --- the smallest assert that does the job ---------------------------------

function assertEqual<T>(actual: T, expected: T, what: string) {
  if (actual !== expected) {
    throw new Error(`${what}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

// --- harness ---------------------------------------------------------------

const results: string[] = [];

function test(name: string, fn: () => void) {
  try {
    fn();
    results.push(`ok   ${name}`);
  } catch (err) {
    results.push(`FAIL ${name}\n     ${err instanceof Error ? err.message : String(err)}`);
  }
}

const FWD = false;
const BACK = true;

// A dialog with three tabbable things in it: the close button, an input, and
// the confirm button. Strings stand in for elements; the seam never inspects
// them, it only compares identity and position.
const panel = ["close", "input", "confirm"];

// --- forward ---------------------------------------------------------------

test("Tab moves to the next element", () => {
  assertEqual(nextTrapFocus(panel, "close", FWD), "input", "close -> input");
  assertEqual(nextTrapFocus(panel, "input", FWD), "confirm", "input -> confirm");
});

test("Tab from the last element wraps to the first", () => {
  assertEqual(nextTrapFocus(panel, "confirm", FWD), "close", "confirm wraps to close");
});

// --- backward --------------------------------------------------------------

test("Shift+Tab moves to the previous element", () => {
  assertEqual(nextTrapFocus(panel, "confirm", BACK), "input", "confirm -> input");
  assertEqual(nextTrapFocus(panel, "input", BACK), "close", "input -> close");
});

test("Shift+Tab from the first element wraps to the last", () => {
  assertEqual(nextTrapFocus(panel, "close", BACK), "confirm", "close wraps to confirm");
});

// --- the recovery cases, which are the whole point -------------------------

test("focus that has escaped the dialog is pulled back inside", () => {
  // This is the live bug: the browser has moved focus to something behind the
  // backdrop, so `current` is not in the list at all. Tab must land back in the
  // panel rather than continuing through the page.
  assertEqual(nextTrapFocus(panel, "page-link-behind-backdrop", FWD), "close",
    "forward recovery lands on the first element");
  assertEqual(nextTrapFocus(panel, "page-link-behind-backdrop", BACK), "confirm",
    "backward recovery lands on the last element");
});

test("nothing focused yet behaves like focus escaped", () => {
  assertEqual(nextTrapFocus(panel, null, FWD), "close", "forward from nothing");
  assertEqual(nextTrapFocus(panel, null, BACK), "confirm", "backward from nothing");
});

// --- degenerate panels -----------------------------------------------------

test("a lone focusable element keeps focus on itself in both directions", () => {
  assertEqual(nextTrapFocus(["only"], "only", FWD), "only", "forward stays put");
  assertEqual(nextTrapFocus(["only"], "only", BACK), "only", "backward stays put");
});

test("a panel with nothing focusable traps nothing", () => {
  // Returning null lets the caller decline to preventDefault, rather than
  // swallowing Tab and stranding the user in a dialog with no exit.
  assertEqual(nextTrapFocus([], "close", FWD), null, "forward on an empty panel");
  assertEqual(nextTrapFocus([], null, BACK), null, "backward on an empty panel");
});

// --- report ----------------------------------------------------------------

const failed = results.filter((r) => r.startsWith("FAIL")).length;
console.log(results.join("\n"));
console.log(`\n${results.length - failed} passed, ${failed} failed`);

if (failed > 0) {
  // Throwing gives node a non-zero exit without needing @types/node for `process`.
  throw new Error(`${failed} focus-trap test(s) failed`);
}
