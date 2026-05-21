import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/types/auth";
import { REVIEWER_ROLES, STAFF_ROLES, type RoleName } from "@/lib/constants";

interface AuthState {
  user:         User | null;
  accessToken:  string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;

  login:  (user: User, access: string, refresh: string) => void;
  logout: () => void;
  updateUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user:            null,
      accessToken:     null,
      refreshToken:    null,
      isAuthenticated: false,

      login: (user, access, refresh) => {
        localStorage.setItem("access_token",  access);
        localStorage.setItem("refresh_token", refresh);
        set({ user, accessToken: access, refreshToken: refresh, isAuthenticated: true });
      },

      logout: () => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
      },

      updateUser: (user) => set({ user }),
    }),
    { name: "iris-auth", partialize: (s) => ({ user: s.user, accessToken: s.accessToken, refreshToken: s.refreshToken, isAuthenticated: s.isAuthenticated }) }
  )
);

// Selector helpers -- use these in components instead of importing constants everywhere
export const useRole    = () => useAuthStore((s) => s.user?.role_name ?? null);
export const useIsReviewer = () => useAuthStore((s) => REVIEWER_ROLES.includes(s.user?.role_name as RoleName));
export const useIsStaff    = () => useAuthStore((s) => STAFF_ROLES.includes(s.user?.role_name as RoleName));
