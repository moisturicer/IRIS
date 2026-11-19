import { safeRedirectPath, wholePath } from "@/lib/redirectTarget";

/** The browser's own lock (NFR-S6): this many rejected credentials in a tab lock it. */
export const LOGIN_FAILURE_LIMIT = 3;

const ATTEMPT_KEY_PREFIX = "iris_login_attempts:";
const LOCKOUT_KEY_PREFIX = "iris_lockout_until:";

function loginKey(identifier: string): string {
  return identifier.trim().toLowerCase();
}

export function getLoginAttempts(identifier: string): number {
  const raw = sessionStorage.getItem(`${ATTEMPT_KEY_PREFIX}${loginKey(identifier)}`);
  return raw ? Number.parseInt(raw, 10) || 0 : 0;
}

export function incrementLoginAttempts(identifier: string): number {
  const key = `${ATTEMPT_KEY_PREFIX}${loginKey(identifier)}`;
  const next = getLoginAttempts(identifier) + 1;
  sessionStorage.setItem(key, String(next));
  return next;
}

export function resetLoginAttempts(identifier: string): void {
  sessionStorage.removeItem(`${ATTEMPT_KEY_PREFIX}${loginKey(identifier)}`);
}

export function setLockoutUntil(identifier: string, unlockAtMs: number): void {
  sessionStorage.setItem(`${LOCKOUT_KEY_PREFIX}${loginKey(identifier)}`, String(unlockAtMs));
}

export function getLockoutUntil(identifier: string): number | null {
  const key = loginKey(identifier);
  const raw = sessionStorage.getItem(`${LOCKOUT_KEY_PREFIX}${key}`);
  if (!raw) return null;
  const ms = Number.parseInt(raw, 10);
  if (Number.isNaN(ms) || ms <= Date.now()) {
    sessionStorage.removeItem(`${LOCKOUT_KEY_PREFIX}${key}`);
    return null;
  }
  return ms;
}

export function isAccountLocked(identifier: string): boolean {
  return getLockoutUntil(identifier) !== null;
}

export function clearLockout(identifier: string): void {
  sessionStorage.removeItem(`${LOCKOUT_KEY_PREFIX}${loginKey(identifier)}`);
}

const SESSION_ACCOUNT_KEY = "iris_session_account";

/**
 * Whose session this tab last held (IR-1242).
 *
 * The login screen sends a person back to the page their session ended on
 * (IR-236), but on a shared lab machine the person signing in next may be
 * someone else, and the page the last account left open is not theirs to land
 * on. The account id is the only thing kept: it says whose page it was, and
 * nothing about it. `sessionStorage` because the idle-timeout path reaches the
 * login screen through a full page load, which nothing in memory survives, and
 * because it ends with the tab.
 *
 * Storage can be unavailable (a locked-down browser); then nothing is known,
 * and the login screen behaves as it did before this was kept.
 */
export function rememberSessionAccount(id: number): void {
  try {
    sessionStorage.setItem(SESSION_ACCOUNT_KEY, String(id));
  } catch {
    // Nothing kept; see above.
  }
}

/** Forgotten on a deliberate sign-out: nobody's page is waiting to be returned to. */
export function forgetSessionAccount(): void {
  try {
    sessionStorage.removeItem(SESSION_ACCOUNT_KEY);
  } catch {
    // Nothing was kept.
  }
}

/** The account this tab last held a session for, or `null` when none is known. */
export function sessionAccount(): number | null {
  try {
    const raw = sessionStorage.getItem(SESSION_ACCOUNT_KEY);
    if (raw === null || !/^\d+$/.test(raw)) return null;
    const id = Number(raw);
    return Number.isSafeInteger(id) ? id : null;
  } catch {
    return null;
  }
}

/**
 * What the login screen says for each reason the server gives for refusing a
 * session (IR-645, `apps/accounts/sessions.py`). Inactivity is the default:
 * it is what a refusal with no reason, or one this list does not know, said
 * before reasons existed.
 */
export const SESSION_END_MESSAGES = {
  session_idle: {
    title: "Session Expired",
    text: "Your session timed out after 30 minutes of inactivity. Please sign in again.",
  },
  session_ended: {
    title: "Signed Out",
    text: "You signed out of this session, perhaps in another tab. Please sign in again.",
  },
  account_locked: {
    title: "Account Locked",
    text: "You were signed out because your account was locked. Contact an administrator to unlock it.",
  },
  session_ended_password_changed: {
    title: "Password Changed",
    text: "You were signed out because your password was changed on another device. Please sign in with your new password.",
  },
  session_ended_revoked: {
    title: "Session Ended",
    text: "An administrator ended this session. Please sign in again, or contact an administrator if you did not expect this.",
  },
} as const;

/**
 * The code the route guard passes when a session stored in this tab could not
 * be restored on load and the server gave no reason the screen knows (IR-1081,
 * audit FB-01). It is the interface's own, never one the server sends, so it
 * is kept out of `SESSION_END_MESSAGES`, which is exactly the server's list.
 */
export const SESSION_LOST_CODE = "session_lost";

const SESSION_LOST_MESSAGE = {
  title: "Session Ended",
  text: "Your session ended. Sign in to continue where you were.",
} as const;

export type SessionEndCode = keyof typeof SESSION_END_MESSAGES;

export function isSessionEndCode(code: unknown): code is SessionEndCode {
  return typeof code === "string" && Object.prototype.hasOwnProperty.call(SESSION_END_MESSAGES, code);
}

export function sessionEndMessage(code: unknown) {
  if (code === SESSION_LOST_CODE) return SESSION_LOST_MESSAGE;
  return SESSION_END_MESSAGES[isSessionEndCode(code) ? code : "session_idle"];
}

/**
 * NFR-S2 — send user to login with session-expired banner.
 *
 * This is a full page load, not a router navigation, so nothing in memory
 * survives it and the page the user was on has to travel in the URL. `?next=`
 * is validated on arrival by `safeRedirectPath`, the same check the router
 * state goes through (IR-236) — the login screen does not trust this value
 * just because we wrote it. `?code=` is why the server refused the session
 * (IR-645); only a code the login screen knows is passed on.
 */
export function redirectToLoginSessionExpired(code?: unknown): void {
  if (window.location.pathname === "/login") return;

  const params = new URLSearchParams({ reason: "session_expired" });
  if (isSessionEndCode(code)) params.set("code", code);
  const next = safeRedirectPath(wholePath(window.location));
  if (next) params.set("next", next);

  window.location.href = `/login?${params}`;
}
