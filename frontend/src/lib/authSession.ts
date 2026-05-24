/** SRS FR-M1-01: lock account after 3 consecutive failed logins */
export const LOGIN_FAILURE_LIMIT = 3;

const ATTEMPT_KEY_PREFIX = "iris_login_attempts:";
const LOCKOUT_KEY_PREFIX = "iris_lockout_until:";

export function getLoginAttempts(email: string): number {
  const raw = sessionStorage.getItem(`${ATTEMPT_KEY_PREFIX}${email.toLowerCase()}`);
  return raw ? Number.parseInt(raw, 10) || 0 : 0;
}

export function incrementLoginAttempts(email: string): number {
  const key = `${ATTEMPT_KEY_PREFIX}${email.toLowerCase()}`;
  const next = getLoginAttempts(email) + 1;
  sessionStorage.setItem(key, String(next));
  return next;
}

export function resetLoginAttempts(email: string): void {
  sessionStorage.removeItem(`${ATTEMPT_KEY_PREFIX}${email.toLowerCase()}`);
}

export function setLockoutUntil(email: string, unlockAtMs: number): void {
  sessionStorage.setItem(`${LOCKOUT_KEY_PREFIX}${email.toLowerCase()}`, String(unlockAtMs));
}

export function getLockoutUntil(email: string): number | null {
  const raw = sessionStorage.getItem(`${LOCKOUT_KEY_PREFIX}${email.toLowerCase()}`);
  if (!raw) return null;
  const ms = Number.parseInt(raw, 10);
  if (Number.isNaN(ms) || ms <= Date.now()) {
    sessionStorage.removeItem(`${LOCKOUT_KEY_PREFIX}${email.toLowerCase()}`);
    return null;
  }
  return ms;
}

export function isAccountLocked(email: string): boolean {
  return getLockoutUntil(email) !== null;
}

export function clearLockout(email: string): void {
  sessionStorage.removeItem(`${LOCKOUT_KEY_PREFIX}${email.toLowerCase()}`);
}

/** NFR-S2 — send user to login with session-expired banner */
export function redirectToLoginSessionExpired(): void {
  if (window.location.pathname !== "/login") {
    window.location.href = "/login?reason=session_expired";
  }
}
