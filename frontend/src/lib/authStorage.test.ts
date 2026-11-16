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
// What builds before the account library kept in this browser: history
// (IR-756), status folders and own folders, and stars (IR-579). Every one is
// deleted, never read or imported (ADR-044 amendments 2026-11-16).
const OLD_LIBRARY_KEYS = ["iris_reading_history", "iris_record_collections", "iris_starred_records", "iris_saved_opportunities"];
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

  // IR-579 changes this test on purpose: it used the old folders key as an
  // example of storage that is not a credential, and that key is now deleted
  // on sign-out (by the auth store, not here). A Discover preference stands in.
  it("leaves storage that is not a credential alone", () => {
    localStorage.setItem("iris.discover.columns", "3");
    sessionStorage.setItem("iris_login_attempts:a@cit.edu", "2");
    sessionStorage.setItem("iris_lockout_until:a@cit.edu", "9999999999999");

    clearAuthSession();

    expect(localStorage.getItem("iris.discover.columns")).toBe("3");
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
    localStorage.setItem("iris_reading_history", JSON.stringify([
      { recordId: 1, title: "A paper", viewedAt: "2026-01-01T00:00:00.000Z" },
    ]));
    localStorage.setItem("iris_record_collections", JSON.stringify([
      { id: "reading", name: "Reading", recordIds: [1] },
      { id: "1730000000000", name: "Old browser folder", recordIds: [2] },
    ]));
    localStorage.setItem("iris_starred_records", JSON.stringify([3]));
    // Calls saved in the browser before they followed the account (IR-766).
    localStorage.setItem("iris_saved_opportunities", JSON.stringify([4]));
  }

  function everyCredentialIsGone() {
    expect(sessionStorage.getItem(REFRESH_KEY)).toBeNull();
    for (const key of LEGACY_KEYS) {
      expect(localStorage.getItem(key)).toBeNull();
      expect(sessionStorage.getItem(key)).toBeNull();
    }
    // The previous person's old library must not greet the next one.
    for (const key of OLD_LIBRARY_KEYS) expect(localStorage.getItem(key)).toBeNull();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  }

  it("sign-in deletes what an older build kept of the library in this browser", () => {
    for (const key of OLD_LIBRARY_KEYS) localStorage.setItem(key, "[1]");

    useAuthStore.getState().login(makeUser(), "access-1", "refresh-1");

    for (const key of OLD_LIBRARY_KEYS) expect(localStorage.getItem(key)).toBeNull();
  });

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
    for (const key of OLD_LIBRARY_KEYS) expect(localStorage.getItem(key)).toBeNull();
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
