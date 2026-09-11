import { safeRedirectPath, wholePath } from "@/lib/redirectTarget";

/** SRS FR-M1-01: lock account after 3 consecutive failed logins */
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

/**
 * NFR-S2 — send user to login with session-expired banner.
 *
 * This is a full page load, not a router navigation, so nothing in memory
 * survives it and the page the user was on has to travel in the URL. `?next=`
 * is validated on arrival by `safeRedirectPath`, the same check the router
 * state goes through (IR-236) — the login screen does not trust this value
 * just because we wrote it.
 */
export function redirectToLoginSessionExpired(): void {
  if (window.location.pathname === "/login") return;

  const next = safeRedirectPath(wholePath(window.location));
  const query = next
    ? `?reason=session_expired&next=${encodeURIComponent(next)}`
    : "?reason=session_expired";

  window.location.href = `/login${query}`;
}
