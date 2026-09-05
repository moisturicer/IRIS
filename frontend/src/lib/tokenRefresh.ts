/**
 * One refresh at a time (IR-159).
 *
 * The server has `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` both on
 * (`config/settings/base.py`). Rotation means a successful refresh *invalidates*
 * the token it was given. So if two requests 401 at the same moment and each
 * refreshes independently, the second presents a token the first has already
 * blacklisted: it fails, and the user is thrown back to the login screen in the
 * middle of a session. Users report that as "it randomly logs me out"; it is
 * really "I loaded a page that fires two requests at once".
 *
 * The fix is a gate, not a retry: the first caller starts the refresh, everyone
 * who arrives while it is in flight waits on the *same* promise, and the token is
 * spent exactly once.
 *
 * This module is deliberately free of axios, storage and React so the gate can
 * be tested on its own -- see `tokenRefresh.test.ts`. It knows nothing about
 * where tokens come from or go; the caller supplies `doRefresh` and decides what
 * to do with the result.
 */

export interface RefreshedTokens {
  access: string;
  /** Present when the server rotated the refresh token, which it does by default. */
  refresh?: string;
}

export type RefreshFn = () => Promise<RefreshedTokens>;

let inFlight: Promise<RefreshedTokens> | null = null;

/**
 * Run `doRefresh`, or join the refresh already running.
 *
 * The gate reopens as soon as the attempt settles, success or failure. Reopening
 * after a failure is intentional: the next 401 may come from a genuinely new
 * session (the user logged back in), and a permanently shut gate would leave
 * that session unable to refresh at all. Guarding against a *retry loop* is the
 * caller's job, and the axios interceptor does it with a per-request `_retry`
 * flag -- one attempt per request, no matter how many requests there are.
 */
export function refreshOnce(doRefresh: RefreshFn): Promise<RefreshedTokens> {
  if (!inFlight) {
    inFlight = doRefresh().finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

/** True while a refresh is in flight. Exposed for diagnostics, not control flow. */
export function isRefreshing(): boolean {
  return inFlight !== null;
}

/**
 * Drop any in-flight refresh.
 *
 * Used by the tests to isolate cases, and on logout so a refresh started by the
 * outgoing session cannot resolve into the incoming one.
 */
export function __resetRefreshState(): void {
  inFlight = null;
}
