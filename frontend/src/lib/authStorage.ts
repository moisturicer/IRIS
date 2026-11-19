/**
 * No token is persisted by the browser's own storage any more (ADR-072).
 *
 * The refresh token lives in an `HttpOnly` cookie the server sets, which page
 * scripts can't read, and the access token lives only in memory. A reload or a
 * new tab restores the session by asking the server (`hydrateAuth`).
 *
 * What remains is clean-up of keys earlier versions wrote. A refresh token left
 * in `localStorage` or `sessionStorage` is a live-looking credential, and on a
 * shared lab machine `localStorage` outlives the tab. Cleared on load and on
 * every logout until no pilot browser can still hold one.
 */
const LEGACY_KEYS = ["iris_refresh_token", "refresh_token", "access_token"] as const;

export function clearAuthSession(): void {
  for (const key of LEGACY_KEYS) {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  }
}
