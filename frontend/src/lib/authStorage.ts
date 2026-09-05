/**
 * The one place a token is persisted.
 *
 * Only the refresh token is stored, and only in `sessionStorage`, so a reload
 * restores the session without leaving the access token on disk (FR-M6-01).
 * Everything else reads tokens from the auth store, never from storage directly.
 */
const REFRESH_KEY = "iris_refresh_token";

/**
 * Keys written by earlier versions that nothing reads any more.
 *
 * `api/client.ts` used to write both of these on every refresh while the rest of
 * the app read from the store, so they were orphans — but orphans that outlive a
 * logout. A refresh token left in `localStorage` is a live credential, and
 * `localStorage` survives closing the tab, which is the case that matters on a
 * shared lab machine. Cleared on every logout until we can be confident no
 * pilot browser still holds one.
 */
const LEGACY_KEYS = ["refresh_token", "access_token"] as const;

export function getStoredRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY);
}

export function setStoredRefreshToken(refresh: string): void {
  sessionStorage.setItem(REFRESH_KEY, refresh);
}

export function clearAuthSession(): void {
  sessionStorage.removeItem(REFRESH_KEY);
  for (const key of LEGACY_KEYS) {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  }
}
