/**
 * Restoring a session on page load, without spending the token twice (IR-238),
 * from the server's HttpOnly cookie (ADR-072, IR-1222).
 *
 * **The bug this pins.** `AuthBootstrap` calls `hydrateAuth()` from an effect,
 * and the app runs under `React.StrictMode`, which double-invokes effects in
 * development. Both invocations would present the same refresh token, and the
 * server has `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` on, so the
 * second got a 401 and called `logout()`, wiping the session the first had just
 * restored. `refreshOnce()` closes that; this file asserts the store is behind it.
 *
 * **ADR-072 changed where the token lives.** It is in an HttpOnly cookie the
 * browser sends and the code can't read, so load always asks the server. A
 * missing cookie answers `no_session`, which is "never signed in", not a lost
 * session. Rewritten for IR-1222 on purpose: the earlier version read and
 * wrote `sessionStorage`, which ADR-072 retires.
 *
 * **The fake server rotates and blacklists like the real one,** and keeps the
 * token in a cookie jar the way the browser would. A stub that accepted the
 * same token twice would pass against the broken code.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "./auth.store";
import { useNoticeStore } from "./notice.store";
import { __resetRefreshState } from "@/lib/tokenRefresh";

/** The browser's cookie jar: the refresh token the server last set, or none. */
const jar: { cookie: string | null } = { cookie: null };
/** Refresh tokens already exchanged, and therefore blacklisted. */
const spent = new Set<string>();
let issued = 0;
let remembered = false;

const refreshToken = vi.fn(async () => {
  const token = jar.cookie;
  if (token === null) {
    throw { response: { status: 401, data: { detail: "Not signed in.", code: "no_session" } } };
  }
  if (spent.has(token)) {
    // What SimpleJWT answers once the token has been rotated away; the server
    // clears the cookie on any refused refresh.
    jar.cookie = null;
    throw { response: { status: 401, data: { detail: "Token is blacklisted" } } };
  }
  spent.add(token);
  issued += 1;
  jar.cookie = `refresh-${issued}`;
  return { data: { access: `access-${issued}`, remembered } };
});

const me = vi.fn(async () => ({
  data: { id: 7, email: "ktto@cit.edu", role_name: "KTTO" },
}));

vi.mock("@/api/auth", () => ({
  authApi: {
    refreshToken: () => refreshToken(),
    me: () => me(),
  },
}));

beforeEach(() => {
  jar.cookie = null;
  spent.clear();
  issued = 0;
  remembered = false;
  refreshToken.mockClear();
  me.mockClear();
  sessionStorage.clear();
  __resetRefreshState();
  useAuthStore.setState({
    user: null,
    accessToken: null,
    remembered: false,
    isAuthenticated: false,
    authReady: false,
    sessionLost: null,
  });
});

describe("hydrateAuth", () => {
  it("spends the cookie once when called twice at the same moment", async () => {
    // StrictMode's double-invoked effect, exactly: two calls, same tick.
    jar.cookie = "refresh-0";

    const { hydrateAuth } = useAuthStore.getState();
    await Promise.all([hydrateAuth(), hydrateAuth()]);

    expect(refreshToken).toHaveBeenCalledTimes(1);

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe("access-1");
    expect(state.authReady).toBe(true);
    expect(jar.cookie).toBe("refresh-1");
  });

  it("presents the rotated cookie when a later call does not overlap", async () => {
    // Not the StrictMode case: a genuinely separate load, after the gate has
    // reopened. The browser sends whatever the server last set.
    jar.cookie = "refresh-0";

    const { hydrateAuth } = useAuthStore.getState();
    await hydrateAuth();
    await hydrateAuth();

    expect(refreshToken).toHaveBeenCalledTimes(2);
    expect(spent).toEqual(new Set(["refresh-0", "refresh-1"]));
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });

  it("restores a session in a new tab: always asks, since the cookie can't be read (ADR-072)", async () => {
    // A new tab starts with nothing in memory or storage; only the cookie.
    jar.cookie = "refresh-0";

    await useAuthStore.getState().hydrateAuth();

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user).toMatchObject({ id: 7 });
  });

  it("records whether the session was kept with Keep me signed in", async () => {
    jar.cookie = "refresh-0";
    remembered = true;

    await useAuthStore.getState().hydrateAuth();

    expect(useAuthStore.getState().remembered).toBe(true);
  });

  it("deletes a token an earlier version stored in sessionStorage", async () => {
    sessionStorage.setItem("iris_refresh_token", "from-before-ADR-072");

    await useAuthStore.getState().hydrateAuth();

    expect(sessionStorage.getItem("iris_refresh_token")).toBeNull();
  });

  it("signs out when the cookie is genuinely rejected", async () => {
    // The gate must not turn a real authentication failure into a session.
    jar.cookie = "refresh-0";
    spent.add("refresh-0");

    await useAuthStore.getState().hydrateAuth();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.authReady).toBe(true);
  });

  it("is ready, signed out and silent, when the browser has no session at all", async () => {
    await useAuthStore.getState().hydrateAuth();

    expect(refreshToken).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().authReady).toBe(true);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().sessionLost).toBeNull();
  });

  it("becomes ready even when the profile request fails", async () => {
    // `authReady` gates the whole router. A path that misses it leaves the app
    // on the bootstrap spinner forever, which reads as a hang, not an error.
    jar.cookie = "refresh-0";
    me.mockRejectedValueOnce(new Error("profile unavailable"));

    await useAuthStore.getState().hydrateAuth();

    expect(useAuthStore.getState().authReady).toBe(true);
  });

  it("keeps the session on a refresh while the data notice is unanswered (IR-790)", async () => {
    // The server refuses `me` until the notice is answered. That is not a
    // broken session: the guard shows the notice and the account loads after.
    jar.cookie = "refresh-0";
    me.mockRejectedValueOnce({ response: { status: 403, data: { code: "notice_acceptance_required" } } });

    await useAuthStore.getState().hydrateAuth();

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe("access-1");
    expect(state.isAuthenticated).toBe(true);
    expect(state.authReady).toBe(true);
    expect(useNoticeStore.getState().required).toBe(true);
    useNoticeStore.setState({ required: false });
  });

  // IR-1081 (audit FB-01): a reload that ends on sign-in must say why.
  describe("when a session cannot be restored", () => {
    it("remembers that a session was lost, so the guard can say so", async () => {
      jar.cookie = "refresh-0";
      spent.add("refresh-0");

      await useAuthStore.getState().hydrateAuth();

      expect(useAuthStore.getState().sessionLost).toEqual({ code: null });
    });

    it("keeps the reason the server gave", async () => {
      jar.cookie = "refresh-0";
      refreshToken.mockRejectedValueOnce({
        response: { status: 401, data: { code: "session_expired" } },
      });

      await useAuthStore.getState().hydrateAuth();

      expect(useAuthStore.getState().sessionLost).toEqual({ code: "session_expired" });
    });

    it("also remembers it when the profile request fails after a good refresh", async () => {
      jar.cookie = "refresh-0";
      me.mockRejectedValueOnce(new Error("profile unavailable"));

      await useAuthStore.getState().hydrateAuth();

      expect(useAuthStore.getState().sessionLost).toEqual({ code: null });
    });

    it("clears the memory on the next sign-in", () => {
      useAuthStore.setState({ sessionLost: { code: null } });

      useAuthStore.getState().login({ id: 7, email: "ktto@cit.edu", role_name: "KTTO" } as never, "access");

      expect(useAuthStore.getState().sessionLost).toBeNull();
    });
  });
});
