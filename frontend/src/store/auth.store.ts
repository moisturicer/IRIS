import { create } from "zustand";
import type { User } from "@/types/auth";
import { authApi } from "@/api/auth";
import {
  clearAuthSession,
  getStoredRefreshToken,
  setStoredRefreshToken,
} from "@/lib/authStorage";
import { __resetRefreshState } from "@/lib/tokenRefresh";
import { REVIEWER_ROLES, STAFF_ROLES, type RoleName } from "@/lib/constants";

interface AuthState {
  user:            User | null;
  accessToken:     string | null;
  refreshToken:    string | null;
  isAuthenticated: boolean;
  /** False until we have checked sessionStorage for a refresh token on load. */
  authReady:       boolean;
  /**
   * Bumped by `logout`/`clearTokens`. `client.ts` captures this before starting a
   * refresh and checks it again after the refresh resolves: if it moved, the
   * session that requested the refresh no longer exists, so the result is
   * discarded instead of reviving a session the user already signed out of.
   * `__resetRefreshState` alone doesn't cover this -- it only stops a *future*
   * caller from joining a stale in-flight promise; it can't reach into the one a
   * request is already `await`ing.
   */
  sessionEpoch: number;

  login:      (user: User, access: string, refresh: string) => void;
  logout:     () => void;
  updateUser: (user: User) => void;
  setTokens:  (access: string, refresh?: string) => void;
  clearTokens: () => void;
  hydrateAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user:            null,
  accessToken:     null,
  refreshToken:    null,
  isAuthenticated: false,
  authReady:       false,
  sessionEpoch:    0,

  login: (user, access, refresh) => {
    setStoredRefreshToken(refresh);
    set({
      user,
      accessToken: access,
      refreshToken: refresh,
      isAuthenticated: true,
    });
  },

  logout: () => {
    // Drop any refresh already in flight so a *future* caller doesn't join it.
    // This alone is not enough: a request already `await`ing the old promise in
    // client.ts still resolves and would otherwise call setTokens after logout,
    // quietly re-authenticating the browser the user just signed out of. Bumping
    // sessionEpoch is what lets that caller notice and discard its result.
    __resetRefreshState();
    clearAuthSession();
    set((s) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionEpoch: s.sessionEpoch + 1,
    }));
  },

  updateUser: (user) => set({ user }),

  setTokens: (access, refresh) => {
    if (refresh) setStoredRefreshToken(refresh);
    set((s) => ({
      accessToken: access,
      refreshToken: refresh ?? s.refreshToken,
      isAuthenticated: true,
    }));
  },

  clearTokens: () => {
    __resetRefreshState();
    clearAuthSession();
    set((s) => ({
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      sessionEpoch: s.sessionEpoch + 1,
    }));
  },

  hydrateAuth: async () => {
    const refresh = getStoredRefreshToken();
    if (!refresh) {
      set({ authReady: true });
      return;
    }

    try {
      const { data: tokenData } = await authApi.refreshToken(refresh);
      const access = tokenData.access as string;
      const newRefresh =
        (tokenData as { refresh?: string }).refresh ?? refresh;

      setStoredRefreshToken(newRefresh);
      set({
        accessToken: access,
        refreshToken: newRefresh,
        isAuthenticated: true,
      });

      const { data: user } = await authApi.me();
      set({ user });
    } catch {
      get().logout();
    } finally {
      set({ authReady: true });
    }
  },
}));

export const useRole    = () => useAuthStore((s) => s.user?.role_name ?? null);
export const useIsReviewer = () => useAuthStore((s) => REVIEWER_ROLES.includes(s.user?.role_name as RoleName));
export const useIsStaff    = () => useAuthStore((s) => STAFF_ROLES.includes(s.user?.role_name as RoleName));
