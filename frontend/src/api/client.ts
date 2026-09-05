import axios, { type InternalAxiosRequestConfig, type AxiosError } from "axios";
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
  const { data } = await axios.post(`${API_BASE}/auth/token/refresh/`, { refresh });
  return { access: data.access, refresh: data.refresh };
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

    const { refreshToken, setTokens, logout } = useAuthStore.getState();
    if (!refreshToken) {
      logout();
      redirectToLoginSessionExpired();
      return Promise.reject(error);
    }

    try {
      // Every request that 401s during the same window joins this one promise, so
      // the refresh token -- which the server rotates and blacklists on use -- is
      // spent exactly once. See lib/tokenRefresh.ts.
      const tokens = await refreshOnce(() => requestNewTokens(refreshToken));

      // Write through the store, which is the single token store: it updates
      // sessionStorage via authStorage and re-renders anything reading auth
      // state. The previous version wrote to localStorage keys that nothing ever
      // read, so the store kept serving the stale access token and every retry
      // 401'd again.
      setTokens(tokens.access, tokens.refresh);

      original.headers!.Authorization = `Bearer ${tokens.access}`;
      return apiClient(original);
    } catch {
      // The refresh itself failed -- expired, rotated out from under us, or the
      // server is down. Nothing to retry with.
      logout();
      redirectToLoginSessionExpired();
      return Promise.reject(error);
    }
  }
);
