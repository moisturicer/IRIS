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

/** NFR-S2 — send user to login with session-expired banner */
export function redirectToLoginSessionExpired(): void {
  if (window.location.pathname !== "/login") {
    window.location.href = "/login?reason=session_expired";
  }
}
