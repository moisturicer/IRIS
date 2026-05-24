/**
 * Persist only the refresh token in sessionStorage so a full page reload can
 * restore the session without keeping the access token on disk (FR-M6-01).
 */
const REFRESH_KEY = "iris_refresh_token";

export function getStoredRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY);
}

export function setStoredRefreshToken(refresh: string): void {
  sessionStorage.setItem(REFRESH_KEY, refresh);
}

export function clearAuthSession(): void {
  sessionStorage.removeItem(REFRESH_KEY);
  // Legacy key from older screens — remove if present
  localStorage.removeItem("refresh_token");
}
