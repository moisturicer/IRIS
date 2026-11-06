/**
 * The browser's own login lock and the session-end messages (IR-916, NFR-S6).
 *
 * The lock is per identifier and per tab (`sessionStorage`), counted before the
 * server is asked, so a wrong password typed three times stops the form without
 * a request. The lock's expiry is read against the clock, so these tests move
 * the clock rather than waiting.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  LOGIN_FAILURE_LIMIT,
  SESSION_END_MESSAGES,
  clearLockout,
  getLockoutUntil,
  getLoginAttempts,
  incrementLoginAttempts,
  isAccountLocked,
  isSessionEndCode,
  redirectToLoginSessionExpired,
  resetLoginAttempts,
  sessionEndMessage,
  setLockoutUntil,
} from "./authSession";

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.useRealTimers());

describe("login attempts", () => {
  it("starts at zero", () => {
    expect(getLoginAttempts("a@cit.edu")).toBe(0);
  });

  it("counts up and returns the new count", () => {
    expect(incrementLoginAttempts("a@cit.edu")).toBe(1);
    expect(incrementLoginAttempts("a@cit.edu")).toBe(2);
    expect(getLoginAttempts("a@cit.edu")).toBe(2);
  });

  it("limits at three, which is what the sign-in screen compares against", () => {
    expect(LOGIN_FAILURE_LIMIT).toBe(3);
  });

  it("keeps each account's count apart", () => {
    incrementLoginAttempts("a@cit.edu");
    incrementLoginAttempts("a@cit.edu");

    expect(getLoginAttempts("b@cit.edu")).toBe(0);
  });

  it("treats case and surrounding spaces as the same account, so retyping cannot dodge the lock", () => {
    incrementLoginAttempts("A@CIT.edu");
    incrementLoginAttempts("  a@cit.edu ");

    expect(getLoginAttempts("a@cit.edu")).toBe(2);
  });

  it("resets to zero", () => {
    incrementLoginAttempts("a@cit.edu");

    resetLoginAttempts("a@cit.edu");

    expect(getLoginAttempts("a@cit.edu")).toBe(0);
  });

  it("reads a corrupted count as zero rather than NaN", () => {
    sessionStorage.setItem("iris_login_attempts:a@cit.edu", "garbage");

    expect(getLoginAttempts("a@cit.edu")).toBe(0);
    expect(incrementLoginAttempts("a@cit.edu")).toBe(1);
  });
});

describe("lockout", () => {
  it("is not locked by default", () => {
    expect(getLockoutUntil("a@cit.edu")).toBeNull();
    expect(isAccountLocked("a@cit.edu")).toBe(false);
  });

  it("is locked until the time it was set to", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000);
    setLockoutUntil("a@cit.edu", 5_000);

    expect(getLockoutUntil("a@cit.edu")).toBe(5_000);
    expect(isAccountLocked("a@cit.edu")).toBe(true);
  });

  it("is per account", () => {
    setLockoutUntil("a@cit.edu", Date.now() + 60_000);

    expect(isAccountLocked("b@cit.edu")).toBe(false);
  });

  it("unlocks when the time passes, and forgets the stored value", () => {
    vi.useFakeTimers();
    vi.setSystemTime(1_000);
    setLockoutUntil("a@cit.edu", 5_000);

    vi.setSystemTime(5_000);

    expect(isAccountLocked("a@cit.edu")).toBe(false);
    expect(sessionStorage.getItem("iris_lockout_until:a@cit.edu")).toBeNull();
  });

  it("is still locked one millisecond before it ends", () => {
    vi.useFakeTimers();
    vi.setSystemTime(4_999);
    setLockoutUntil("a@cit.edu", 5_000);

    expect(isAccountLocked("a@cit.edu")).toBe(true);
  });

  it("treats a corrupted value as unlocked and removes it", () => {
    sessionStorage.setItem("iris_lockout_until:a@cit.edu", "soon");

    expect(isAccountLocked("a@cit.edu")).toBe(false);
    expect(sessionStorage.getItem("iris_lockout_until:a@cit.edu")).toBeNull();
  });

  it("can be cleared", () => {
    setLockoutUntil("a@cit.edu", Date.now() + 60_000);

    clearLockout("a@cit.edu");

    expect(isAccountLocked("a@cit.edu")).toBe(false);
  });

  it("does not share state with the attempt counter", () => {
    incrementLoginAttempts("a@cit.edu");
    setLockoutUntil("a@cit.edu", Date.now() + 60_000);

    clearLockout("a@cit.edu");

    expect(getLoginAttempts("a@cit.edu")).toBe(1);
  });
});

describe("session end messages", () => {
  it.each([
    ["session_idle", "Session Expired"],
    ["session_ended", "Signed Out"],
    ["account_locked", "Account Locked"],
    ["session_ended_password_changed", "Password Changed"],
    ["session_ended_revoked", "Session Ended"],
  ])("says %s as %j", (code, title) => {
    expect(isSessionEndCode(code)).toBe(true);
    expect(sessionEndMessage(code).title).toBe(title);
  });

  it("knows exactly the five codes the server gives", () => {
    expect(Object.keys(SESSION_END_MESSAGES).sort()).toEqual([
      "account_locked", "session_ended", "session_ended_password_changed",
      "session_ended_revoked", "session_idle",
    ]);
  });

  it.each([undefined, null, 42, "", "made_up", "toString", "__proto__"])(
    "falls back to inactivity for %j",
    (code) => {
      expect(isSessionEndCode(code)).toBe(false);
      expect(sessionEndMessage(code)).toBe(SESSION_END_MESSAGES.session_idle);
    },
  );
});

describe("redirectToLoginSessionExpired", () => {
  const original = window.location;

  function stubLocation(pathname: string, search = "", hash = "") {
    const loc = { pathname, search, hash, origin: "http://localhost", href: "" };
    Object.defineProperty(window, "location", { configurable: true, value: loc });
    return loc;
  }

  afterEach(() => {
    Object.defineProperty(window, "location", { configurable: true, value: original });
  });

  it("goes to /login with the reason and the page the person was on", () => {
    const loc = stubLocation("/records/42", "?page=3", "#abstract");

    redirectToLoginSessionExpired();

    const url = new URL(loc.href, "http://localhost");
    expect(url.pathname).toBe("/login");
    expect(url.searchParams.get("reason")).toBe("session_expired");
    expect(url.searchParams.get("next")).toBe("/records/42?page=3#abstract");
    expect(url.searchParams.has("code")).toBe(false);
  });

  it("passes on a code the login screen knows", () => {
    const loc = stubLocation("/records/42");

    redirectToLoginSessionExpired("session_ended_revoked");

    expect(new URL(loc.href, "http://localhost").searchParams.get("code")).toBe("session_ended_revoked");
  });

  it("drops a code it does not know rather than echoing it into the URL", () => {
    const loc = stubLocation("/records/42");

    redirectToLoginSessionExpired("<script>");

    expect(new URL(loc.href, "http://localhost").searchParams.has("code")).toBe(false);
  });

  it("does not redirect from the login page itself, which would loop", () => {
    const loc = stubLocation("/login");

    redirectToLoginSessionExpired("session_idle");

    expect(loc.href).toBe("");
  });
});
