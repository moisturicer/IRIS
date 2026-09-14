/**
 * Tests for the logout-during-in-flight-refresh race (IR-159 follow-up).
 *
 * Runs under vitest: `npm test` from `frontend/` (IR-210). This file predates
 * the runner and was executed by a hand-written esbuild-plus-node incantation;
 * its assertions are unchanged, only the harness around them is now real.
 * Two things `tokenRefresh.test.ts` didn't need to work around, because this
 * file pulls in the real store rather than an isolated module:
 * `--define:import.meta.env={}` stands in for the Vite-injected env object that
 * `lib/constants.ts` reads `VITE_API_BASE_URL` from; and `authStorage.ts` reads
 * `sessionStorage`/`localStorage` directly, which Node does not provide by
 * default -- the tiny stubs below exist only so this file can import the real
 * store, not to test storage itself.
 *
 * Why this deserves a test: `client.ts`'s response interceptor starts a token
 * refresh, `await`s it, then calls `setTokens`. If `logout()` runs while that
 * `await` is still pending, the promise resolves anyway and, without a check,
 * would call `setTokens` after logout already cleared everything -- quietly
 * re-authenticating a browser the user just signed out of. `sessionEpoch` is the
 * mechanism that lets the interceptor notice; this proves the mechanism itself
 * fires exactly when it must.
 */
export {}; // every import below is dynamic, so this file needs its own module marker

// --- minimal storage stubs, only so auth.store.ts's imports don't throw ----

function makeStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
    clear: () => data.clear(),
    key: () => null,
    get length() {
      return data.size;
    },
  } as Storage;
}

const g = globalThis as unknown as { sessionStorage?: Storage; localStorage?: Storage };
g.sessionStorage ??= makeStorage();
g.localStorage ??= makeStorage();

const { useAuthStore } = await import("./auth.store");
const { refreshOnce, __resetRefreshState } = await import("../lib/tokenRefresh");

import { beforeEach, test } from "vitest";

// The hand-rolled harness called this before every case; vitest needs it
// said once, here, or the cases leak refresh state into each other.
beforeEach(() => {
  __resetRefreshState();
});

// --- the smallest assert that does the job ---------------------------------

function assertEqual<T>(actual: T, expected: T, what: string) {
  if (actual !== expected) {
    throw new Error(`${what}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

// --- cases -----------------------------------------------------------------

test("logout bumps sessionEpoch even while a refresh is in flight", async () => {
  const epochBefore = useAuthStore.getState().sessionEpoch;

  let release!: (v: { access: string }) => void;
  const pending = refreshOnce(
    () => new Promise((resolve) => { release = resolve; })
  );

  // The request that started `pending` would have captured `epochBefore` right
  // here, exactly as client.ts does, before its `await` below settles.
  useAuthStore.getState().logout();

  release({ access: "resolved-after-logout" });
  await pending;

  const epochAfter = useAuthStore.getState().sessionEpoch;
  if (epochAfter === epochBefore) {
    throw new Error(
      "sessionEpoch did not change across logout -- a refresh that resolves " +
      "after this point would be indistinguishable from one started by the " +
      "current session, and client.ts would wrongly call setTokens with it"
    );
  }

  // What client.ts's interceptor checks after the `await` above returns.
  assertEqual(
    useAuthStore.getState().sessionEpoch !== epochBefore,
    true,
    "interceptor's stale-refresh check must trip for a pre-logout epoch"
  );
});

test("a refresh started after logout is not flagged stale", async () => {
  useAuthStore.getState().logout();
  const epochBefore = useAuthStore.getState().sessionEpoch;

  let release!: (v: { access: string }) => void;
  const pending = refreshOnce(
    () => new Promise((resolve) => { release = resolve; })
  );
  release({ access: "fresh-session-token" });
  await pending;

  assertEqual(
    useAuthStore.getState().sessionEpoch === epochBefore,
    true,
    "a refresh with no logout in between must not be treated as stale"
  );
});

test("clearTokens bumps sessionEpoch the same way logout does", async () => {
  const epochBefore = useAuthStore.getState().sessionEpoch;
  useAuthStore.getState().clearTokens();
  assertEqual(
    useAuthStore.getState().sessionEpoch !== epochBefore,
    true,
    "clearTokens shares logout's clearing path and must share this guard too"
  );
});

// --- report ----------------------------------------------------------------
