import axios, { isAxiosError, type InternalAxiosRequestConfig, type AxiosError } from "axios";
import { IDLE_HEADER, idleSeconds, markReported } from "@/lib/activity";
import { API_BASE } from "@/lib/constants";
import { redirectToLoginSessionExpired } from "@/lib/authSession";
import { refreshOnce, type RefreshedTokens } from "@/lib/tokenRefresh";
import { useAuthStore } from "@/store/auth.store";

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // How long the user has been idle, so a poll cannot keep the session alive
  // (IR-166, NFR-S2). See lib/activity.ts.
  if (config.headers) config.headers[IDLE_HEADER] = String(idleSeconds());
  markReported();
  return config;
});

/**
 * Exchange the stored refresh token for a new pair.
 *
 * Uses bare `axios`, not `apiClient`: routing this through the instance would
 * send it back through the interceptor below, so a 401 on the refresh endpoint
 * itself would try to refresh, recursively.
 */
async function requestNewTokens(refresh: string): Promise<RefreshedTokens> {
  // The idle header here too: this refresh is usually caused by a poll's 401,
  // and counting it as activity would hand the poll the session back.
  const { data } = await axios.post(
    `${API_BASE}/auth/token/refresh/`,
    { refresh },
    { headers: { [IDLE_HEADER]: String(idleSeconds()) } },
  );
  return { access: data.access, refresh: data.refresh };
}

/**
 * A new access token for a request that just 401'd, or null when the session is
 * over. Shared by `apiClient` and the Ask IRIS streams, which use `fetch`
 * (IR-634). On null the user has already been logged out and redirected, or
 * logged out while the refresh was in flight.
 */
export async function refreshSession(): Promise<string | null> {
  const { refreshToken, setTokens, logout } = useAuthStore.getState();
  if (!refreshToken) {
    logout();
    redirectToLoginSessionExpired();
    return null;
  }

  // Captured before the refresh starts so a logout that lands while it is in
  // flight can be detected once it settles -- see auth.store.ts's sessionEpoch.
  const epochAtRefreshStart = useAuthStore.getState().sessionEpoch;

  try {
    // Every request that 401s during the same window joins this one promise, so
    // the refresh token -- which the server rotates and blacklists on use -- is
    // spent exactly once. See lib/tokenRefresh.ts.
    const tokens = await refreshOnce(() => requestNewTokens(refreshToken));

    if (useAuthStore.getState().sessionEpoch !== epochAtRefreshStart) {
      // The session that asked for this refresh was logged out while it was in
      // flight. Applying the result now would silently re-authenticate a
      // browser the user already signed out of -- discard it instead.
      return null;
    }

    // Write through the store, which is the single token store: it updates
    // sessionStorage via authStorage and re-renders anything reading auth
    // state. The previous version wrote to localStorage keys that nothing ever
    // read, so the store kept serving the stale access token and every retry
    // 401'd again.
    setTokens(tokens.access, tokens.refresh);
    return tokens.access;
  } catch (err) {
    // The refresh itself failed -- expired, idle (IR-166), signed out, rotated
    // out from under us, or the server is down. Nothing to retry with. When the
    // server said why, the login screen says it too (IR-645).
    logout();
    redirectToLoginSessionExpired(isAxiosError(err) ? err.response?.data?.code : undefined);
    return null;
  }
}

apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status !== 401 || original?._retry) {
      return Promise.reject(error);
    }

    // One retry per request. The gate in `refreshOnce` stops N requests causing N
    // refreshes; this stops any single request retrying forever.
    original._retry = true;

    const access = await refreshSession();
    if (!access) return Promise.reject(error);

    original.headers!.Authorization = `Bearer ${access}`;
    return apiClient(original);
  }
);
