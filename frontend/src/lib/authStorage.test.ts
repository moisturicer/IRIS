/**
 * What is persisted on sign-in and what sign-out removes (IR-916).
 *
 * The credential inventory is the point. A refresh token left behind is a live
 * session for the next person on a shared lab machine, so every key the app has
 * ever written one to is named here and asserted gone after `clearAuthSession`
 * and after the store's `logout` and `clearTokens`, which are the paths the UI
 * and the 401 handler actually take.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  clearAuthSession,
  getStoredRefreshToken,
  setStoredRefreshToken,
} from "./authStorage";
import { useAuthStore } from "@/store/auth.store";
import { makeUser } from "@/test/authFixtures";

const REFRESH_KEY = "iris_refresh_token";
const HISTORY_KEY = "iris_reading_history";
const LEGACY_KEYS = ["refresh_token", "access_token"];

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  useAuthStore.setState({
    user: null, accessToken: null, refreshToken: null, isAuthenticated: false,
  });
});

describe("the stored refresh token", () => {
  it("is empty before anything is stored", () => {
    expect(getStoredRefreshToken()).toBeNull();
  });

  it("round-trips through sessionStorage and nowhere else", () => {
    setStoredRefreshToken("r1");

    expect(getStoredRefreshToken()).toBe("r1");
    expect(sessionStorage.getItem(REFRESH_KEY)).toBe("r1");
    // localStorage survives closing the tab; the refresh token must not.
    expect(localStorage.length).toBe(0);
  });

  it("is replaced, not appended to, when rotated", () => {
    setStoredRefreshToken("r1");
    setStoredRefreshToken("r2");

    expect(getStoredRefreshToken()).toBe("r2");
    expect(sessionStorage.length).toBe(1);
  });
});

describe("clearAuthSession", () => {
  it("removes the refresh token", () => {
    setStoredRefreshToken("r1");

    clearAuthSession();

    expect(getStoredRefreshToken()).toBeNull();
  });

  it.each(LEGACY_KEYS)("removes the legacy %s from localStorage and sessionStorage", (key) => {
    localStorage.setItem(key, "old-credential");
    sessionStorage.setItem(key, "old-credential");

    clearAuthSession();

    expect(localStorage.getItem(key)).toBeNull();
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  it("leaves storage that is not a credential alone", () => {
    localStorage.setItem("iris_record_collections", "[]");
    sessionStorage.setItem("iris_login_attempts:a@cit.edu", "2");
    sessionStorage.setItem("iris_lockout_until:a@cit.edu", "9999999999999");

    clearAuthSession();

    expect(localStorage.getItem("iris_record_collections")).toBe("[]");
    // The browser's lock must not be a thing signing out can reset.
    expect(sessionStorage.getItem("iris_login_attempts:a@cit.edu")).toBe("2");
    expect(sessionStorage.getItem("iris_lockout_until:a@cit.edu")).toBe("9999999999999");
  });

  it("is safe to call with nothing stored", () => {
    expect(() => clearAuthSession()).not.toThrow();
  });
});

describe("sign-out clears every stored credential", () => {
  function signInAndLeaveEverythingBehind() {
    useAuthStore.getState().login(makeUser(), "access-1", "refresh-1");
    for (const key of LEGACY_KEYS) {
      localStorage.setItem(key, "old-credential");
      sessionStorage.setItem(key, "old-credential");
    }
    localStorage.setItem(HISTORY_KEY, JSON.stringify([
      { recordId: 1, title: "A paper", viewedAt: "2026-01-01T00:00:00.000Z" },
    ]));
  }

  function everyCredentialIsGone() {
    expect(sessionStorage.getItem(REFRESH_KEY)).toBeNull();
    for (const key of LEGACY_KEYS) {
      expect(localStorage.getItem(key)).toBeNull();
      expect(sessionStorage.getItem(key)).toBeNull();
    }
    // The previous person's reading history must not greet the next one.
    expect(localStorage.getItem(HISTORY_KEY)).toBeNull();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  }

  it("sign-in persists only the refresh token", () => {
    useAuthStore.getState().login(makeUser(), "access-1", "refresh-1");

    expect(sessionStorage.getItem(REFRESH_KEY)).toBe("refresh-1");
    // Every stored key and value, read through the Storage API: the refresh
    // token is there, and the access token is in none of them.
    const stored = [sessionStorage, localStorage].flatMap((storage) =>
      Array.from({ length: storage.length }, (_, i) => {
        const key = storage.key(i)!;
        return [key, storage.getItem(key)];
      }),
    );
    expect(stored).toContainEqual([REFRESH_KEY, "refresh-1"]);
    expect(stored.flat()).not.toContain("access-1");
  });

  it("logout leaves nothing behind", () => {
    signInAndLeaveEverythingBehind();

    useAuthStore.getState().logout();

    everyCredentialIsGone();
  });

  it("clearTokens, the session-end path, leaves nothing behind either", () => {
    signInAndLeaveEverythingBehind();

    useAuthStore.getState().clearTokens();

    expect(sessionStorage.getItem(REFRESH_KEY)).toBeNull();
    for (const key of LEGACY_KEYS) {
      expect(localStorage.getItem(key)).toBeNull();
      expect(sessionStorage.getItem(key)).toBeNull();
    }
    expect(localStorage.getItem(HISTORY_KEY)).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("a rotated refresh token is cleared too, not only the first one", () => {
    signInAndLeaveEverythingBehind();
    useAuthStore.getState().setTokens("access-2", "refresh-2");

    useAuthStore.getState().logout();

    everyCredentialIsGone();
  });
});
