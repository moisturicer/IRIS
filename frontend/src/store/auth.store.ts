import { create } from "zustand";
import type { User } from "@/types/auth";
import { REVIEWER_ROLES, STAFF_ROLES, type RoleName } from "@/lib/constants";

interface AuthState {
  user:            User | null;
  accessToken:     string | null;
  refreshToken:    string | null;
  isAuthenticated: boolean;

  login:      (user: User, access: string, refresh: string) => void;
  logout:     () => void;
  updateUser: (user: User) => void;
  setTokens:  (access: string, refresh?: string) => void;
  clearTokens: () => void;
}

/** JWT tokens live in memory only — never localStorage/sessionStorage (SRS FR-M6-01). */
export const useAuthStore = create<AuthState>()((set) => ({
  user:            null,
  accessToken:     null,
  refreshToken:    null,
  isAuthenticated: false,

  login: (user, access, refresh) =>
    set({ user, accessToken: access, refreshToken: refresh, isAuthenticated: true }),

  logout: () =>
    set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false }),

  updateUser: (user) => set({ user }),

  setTokens: (access, refresh) =>
    set((s) => ({
      accessToken: access,
      refreshToken: refresh ?? s.refreshToken,
      isAuthenticated: true,
    })),

  clearTokens: () =>
    set({ accessToken: null, refreshToken: null, isAuthenticated: false }),
}));

export const useRole    = () => useAuthStore((s) => s.user?.role_name ?? null);
export const useIsReviewer = () => useAuthStore((s) => REVIEWER_ROLES.includes(s.user?.role_name as RoleName));
export const useIsStaff    = () => useAuthStore((s) => STAFF_ROLES.includes(s.user?.role_name as RoleName));
