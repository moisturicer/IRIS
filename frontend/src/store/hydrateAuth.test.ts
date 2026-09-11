/**
 * Restoring a session on page load, without spending the token twice (IR-238).
 *
 * **The bug this pins.** `AuthBootstrap` calls `hydrateAuth()` from an effect,
 * and the app runs under `React.StrictMode`, which double-invokes effects in
 * development. `hydrateAuth` was the one refresh path that did not go through
 * `refreshOnce()`, so both invocations read the same stored token and both
 * presented it. The server has `ROTATE_REFRESH_TOKENS` and
 * `BLACKLIST_AFTER_ROTATION` on, so the first call invalidated the token the
 * second was still holding: the second got a 401, fell into `catch`, and called
 * `logout()` — wiping the session the first had just restored. The reviewer
 * landed on the login screen after a plain reload.
 *
 * IR-159 had already built the gate for exactly this and written the symptom
 * down in `lib/tokenRefresh.ts` ("users report that as *it randomly logs me
 * out*"). This file is the assertion that the store is behind it too.
 *
 * **The fake server below rotates and blacklists like the real one.** A test
 * whose stub happily accepts the same refresh token twice would pass against
 * the broken code, which is the whole difficulty of this bug.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "./auth.store";
import { __resetRefreshState } from "@/lib/tokenRefresh";

const REFRESH_KEY = "iris_refresh_token";

/** Refresh tokens already exchanged, and therefore blacklisted. */
const spent = new Set<string>();
let issued = 0;

const refreshToken = vi.fn(async (token: string) => {
  if (spent.has(token)) {
    // What SimpleJWT actually answers once the token has been rotated away.
    throw {
      response: { status: 401, data: { detail: "Token is blacklisted" } },
    };
  }
  spent.add(token);
  issued += 1;
  return { data: { access: `access-${issued}`, refresh: `refresh-${issued}` } };
});

const me = vi.fn(async () => ({
  data: { id: 7, email: "ktto@cit.edu", role_name: "KTTO" },
}));

vi.mock("@/api/auth", () => ({
  authApi: {
    refreshToken: (token: string) => refreshToken(token),
    me: () => me(),
  },
}));

beforeEach(() => {
  spent.clear();
  issued = 0;
  refreshToken.mockClear();
  me.mockClear();
  sessionStorage.clear();
  __resetRefreshState();
  useAuthStore.setState({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    authReady: false,
  });
});

describe("hydrateAuth", () => {
  it("spends the stored token once when called twice at the same moment", async () => {
    // StrictMode's double-invoked effect, exactly: two calls, same tick.
    sessionStorage.setItem(REFRESH_KEY, "refresh-0");

    const { hydrateAuth } = useAuthStore.getState();
    await Promise.all([hydrateAuth(), hydrateAuth()]);

    expect(refreshToken).toHaveBeenCalledTimes(1);

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe("access-1");
    expect(state.authReady).toBe(true);
  });

  it("keeps the rotated token, not the one that was spent", async () => {
    sessionStorage.setItem(REFRESH_KEY, "refresh-0");

    const { hydrateAuth } = useAuthStore.getState();
    await Promise.all([hydrateAuth(), hydrateAuth()]);

    // Leaving the spent token in storage would move the failure to the next
    // reload rather than fixing it.
    expect(sessionStorage.getItem(REFRESH_KEY)).toBe("refresh-1");
  });

  it("uses the rotated token when a later call does not overlap", async () => {
    // Not the StrictMode case: a genuinely separate load, after the gate has
    // reopened. It must read storage again rather than reuse a captured token.
    sessionStorage.setItem(REFRESH_KEY, "refresh-0");

    const { hydrateAuth } = useAuthStore.getState();
    await hydrateAuth();
    await hydrateAuth();

    expect(refreshToken).toHaveBeenCalledTimes(2);
    expect(refreshToken).toHaveBeenLastCalledWith("refresh-1");
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it("signs out when the stored token is genuinely rejected", async () => {
    // The gate must not turn a real authentication failure into a session.
    sessionStorage.setItem(REFRESH_KEY, "refresh-0");
    spent.add("refresh-0");

    await useAuthStore.getState().hydrateAuth();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.authReady).toBe(true);
  });

  it("is ready, and silent, when there was no stored token at all", async () => {
    await useAuthStore.getState().hydrateAuth();

    expect(refreshToken).not.toHaveBeenCalled();
    expect(useAuthStore.getState().authReady).toBe(true);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("becomes ready even when the profile request fails", async () => {
    // `authReady` gates the whole router. A path that misses it leaves the app
    // on the bootstrap spinner forever, which reads as a hang, not an error.
    sessionStorage.setItem(REFRESH_KEY, "refresh-0");
    me.mockRejectedValueOnce(new Error("profile unavailable"));

    await useAuthStore.getState().hydrateAuth();

    expect(useAuthStore.getState().authReady).toBe(true);
  });
});
