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
    // Drop any refresh already in flight. Without this, a refresh started by the
    // outgoing session can resolve after logout and call setTokens, quietly
    // re-authenticating the browser the user just signed out of.
    __resetRefreshState();
    clearAuthSession();
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
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
    set({ accessToken: null, refreshToken: null, isAuthenticated: false });
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
