/**
 * What the browser's own storage holds of a sign-in: nothing (ADR-072, IR-1222).
 *
 * The refresh token lives in an HttpOnly cookie the server sets, which page
 * scripts can't read, and the access token only in memory. A token left in
 * `localStorage` or `sessionStorage` is a live-looking credential for the next
 * person on a shared lab machine, so every key the app has ever written one to
 * is named here and asserted gone on sign-in and after `logout` and
 * `clearTokens`, the paths the UI and the 401 handler take.
 *
 * Rewritten for IR-1222 on purpose: the earlier version asserted that the
 * refresh token round-tripped through `sessionStorage`, which ADR-072 retires.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { clearAuthSession } from "./authStorage";
import { useAuthStore } from "@/store/auth.store";
import { makeUser } from "@/test/authFixtures";

/** The `sessionStorage` key ADR-072 retires. */
const LEGACY_KEY = "iris_refresh_token";

// Every key a refresh or access token was ever stored under: the
// `sessionStorage` key ADR-072 retires, and two older orphans.
const TOKEN_KEYS = ["iris_refresh_token", "refresh_token", "access_token"];
// What builds before the account library kept in this browser: history
// (IR-756), status folders and own folders, and stars (IR-579). Every one is
// deleted, never read or imported (ADR-044 amendments 2026-11-16).
const OLD_LIBRARY_KEYS = ["iris_reading_history", "iris_record_collections", "iris_starred_records", "iris_saved_opportunities"];

function storedEntries(): [string, string | null][] {
  return [sessionStorage, localStorage].flatMap((storage) =>
    Array.from({ length: storage.length }, (_, i) => {
      const key = storage.key(i)!;
      return [key, storage.getItem(key)] as [string, string | null];
    }),
  );
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  useAuthStore.setState({ user: null, accessToken: null, remembered: false, isAuthenticated: false });
});

describe("clearAuthSession", () => {
  it.each(TOKEN_KEYS)("removes %s from localStorage and sessionStorage", (key) => {
    localStorage.setItem(key, "old-credential");
    sessionStorage.setItem(key, "old-credential");

    clearAuthSession();

    expect(localStorage.getItem(key)).toBeNull();
    expect(sessionStorage.getItem(key)).toBeNull();
  });

  // IR-579 changed this test on purpose: it used the old folders key as an
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

describe("a sign-in stores no token in the browser", () => {
  it("keeps the access token in memory only, and stores nothing of the session", () => {
    useAuthStore.getState().login(makeUser(), "access-1", true);

    expect(useAuthStore.getState().accessToken).toBe("access-1");
    expect(useAuthStore.getState().remembered).toBe(true);
    expect(storedEntries().flat()).not.toContain("access-1");
    for (const key of TOKEN_KEYS) {
      expect(localStorage.getItem(key)).toBeNull();
      expect(sessionStorage.getItem(key)).toBeNull();
    }
  });

  it("deletes a token an earlier version stored", () => {
    sessionStorage.setItem(LEGACY_KEY, "x"); // Any value: only its removal matters

    useAuthStore.getState().login(makeUser(), "access-1");

    expect(sessionStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it("deletes what an older build kept of the library in this browser", () => {
    for (const key of OLD_LIBRARY_KEYS) localStorage.setItem(key, "[1]");

    useAuthStore.getState().login(makeUser(), "access-1");

    for (const key of OLD_LIBRARY_KEYS) expect(localStorage.getItem(key)).toBeNull();
  });
});

describe("sign-out clears everything the browser held", () => {
  function signInAndLeaveEverythingBehind() {
    useAuthStore.getState().login(makeUser(), "access-1", true);
    for (const key of TOKEN_KEYS) {
      localStorage.setItem(key, "old-credential");
      sessionStorage.setItem(key, "old-credential");
    }
    for (const key of OLD_LIBRARY_KEYS) localStorage.setItem(key, "[1]");
  }

  function everythingIsGone() {
    for (const key of TOKEN_KEYS) {
      expect(localStorage.getItem(key)).toBeNull();
      expect(sessionStorage.getItem(key)).toBeNull();
    }
    // The previous person's old library must not greet the next one.
    for (const key of OLD_LIBRARY_KEYS) expect(localStorage.getItem(key)).toBeNull();
    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.remembered).toBe(false);
    expect(state.isAuthenticated).toBe(false);
  }

  it("logout leaves nothing behind", () => {
    signInAndLeaveEverythingBehind();

    useAuthStore.getState().logout();

    everythingIsGone();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("clearTokens, the session-end path, leaves nothing behind either", () => {
    signInAndLeaveEverythingBehind();

    useAuthStore.getState().clearTokens();

    everythingIsGone();
  });
});
