/**
 * Tests for the refresh-deduplication seam (IR-159).
 *
 * There is no test runner in this repo yet (IR-82 / IR-163). Run these today with:
 *
 *   docker exec iris-frontend-1 sh -c "cd /app && \
 *     ./node_modules/.bin/esbuild src/lib/tokenRefresh.test.ts \
 *       --bundle --platform=node --format=esm --outfile=/tmp/t.mjs && node /tmp/t.mjs"
 *
 * esbuild is already present as a Vite dependency, so this adds nothing to
 * package.json. The assertions are hand-rolled rather than `node:assert` on
 * purpose: `npm run build` runs `tsc` across `src/`, there is no `@types/node`,
 * and a test file that breaks the production build would be a bad trade for four
 * lines of convenience. When a runner lands, each `test(...)` becomes an `it(...)`.
 *
 * Why this deserves a test at all: with ROTATE_REFRESH_TOKENS and
 * BLACKLIST_AFTER_ROTATION both enabled server-side, a *second* concurrent
 * refresh presents a token the first has already blacklisted. It fails, and the
 * user is logged out mid-session. That is the "random logouts" symptom, and it
 * only appears when two requests 401 at once -- exactly what a dashboard firing
 * parallel calls does. Clicking around will not surface it.
 */
import { refreshOnce, __resetRefreshState, type RefreshedTokens } from "./tokenRefresh";

// --- the smallest assert that does the job ---------------------------------

function assertEqual<T>(actual: T, expected: T, what: string) {
  if (actual !== expected) {
    throw new Error(`${what}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

function assertSame(a: RefreshedTokens, b: RefreshedTokens, what: string) {
  if (a !== b && (a.access !== b.access || a.refresh !== b.refresh)) {
    throw new Error(`${what}: ${JSON.stringify(a)} !== ${JSON.stringify(b)}`);
  }
}

async function assertRejects(p: Promise<unknown>, match: string, what: string) {
  try {
    await p;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (!message.includes(match)) {
      throw new Error(`${what}: rejected with "${message}", expected to include "${match}"`);
    }
    return;
  }
  throw new Error(`${what}: resolved, expected a rejection`);
}

// --- harness ---------------------------------------------------------------

const results: string[] = [];

async function test(name: string, fn: () => Promise<void>) {
  __resetRefreshState();
  try {
    await fn();
    results.push(`ok   ${name}`);
  } catch (err) {
    results.push(`FAIL ${name}\n     ${err instanceof Error ? err.message : String(err)}`);
  }
}

/** A refresh that resolves only when we say so, and counts its invocations. */
function deferredRefresh() {
  let calls = 0;
  let release!: (value: RefreshedTokens) => void;
  let fail!: (reason: Error) => void;
  const fn = () => {
    calls += 1;
    return new Promise<RefreshedTokens>((resolve, reject) => {
      release = resolve;
      fail = reject;
    });
  };
  return {
    fn,
    get calls() {
      return calls;
    },
    release: (v: RefreshedTokens) => release(v),
    fail: (e: Error) => fail(e),
  };
}

// --- cases -----------------------------------------------------------------

await test("concurrent callers share one in-flight refresh", async () => {
  const r = deferredRefresh();

  const a = refreshOnce(r.fn);
  const b = refreshOnce(r.fn);
  const c = refreshOnce(r.fn);

  assertEqual(r.calls, 1, "refresh call count while three callers waited");

  r.release({ access: "new-access", refresh: "new-refresh" });
  const [ra, rb, rc] = await Promise.all([a, b, c]);

  assertEqual(ra.access, "new-access", "first caller's access token");
  assertSame(ra, rb, "second caller got a different result");
  assertSame(rb, rc, "third caller got a different result");
});

await test("a later refresh starts fresh once the first has settled", async () => {
  const first = deferredRefresh();
  const p = refreshOnce(first.fn);
  first.release({ access: "one" });
  await p;

  const second = deferredRefresh();
  const q = refreshOnce(second.fn);
  second.release({ access: "two" });

  assertEqual((await q).access, "two", "in-flight promise was not cleared after settling");
  assertEqual(second.calls, 1, "second refresh call count");
});

await test("a rejected refresh reaches every waiter", async () => {
  const r = deferredRefresh();
  const a = refreshOnce(r.fn);
  const b = refreshOnce(r.fn);

  r.fail(new Error("token blacklisted"));

  await assertRejects(a, "token blacklisted", "first waiter");
  await assertRejects(b, "token blacklisted", "second waiter");
  assertEqual(r.calls, 1, "a failure must not fan out into several refresh attempts");
});

await test("the gate reopens after a failure so a fresh login can refresh again", async () => {
  const failing = deferredRefresh();
  const a = refreshOnce(failing.fn);
  failing.fail(new Error("nope"));
  await assertRejects(a, "nope", "the failing attempt");

  const ok = deferredRefresh();
  const b = refreshOnce(ok.fn);
  ok.release({ access: "recovered" });

  assertEqual((await b).access, "recovered", "the gate stayed shut after a failure");
});

// --- report ----------------------------------------------------------------

const failed = results.filter((r) => r.startsWith("FAIL")).length;
console.log(results.join("\n"));
console.log(`\n${results.length - failed} passed, ${failed} failed`);

if (failed > 0) {
  // Throwing gives node a non-zero exit without needing @types/node for `process`.
  throw new Error(`${failed} token-refresh test(s) failed`);
}
