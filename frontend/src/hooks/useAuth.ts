import { useAuthStore } from "@/store/auth.store";

export function useAuth() {
  const { user, isAuthenticated, login, logout, updateUser } = useAuthStore();
  const refreshToken = useAuthStore((s) => s.refreshToken);
  return { user, isAuthenticated, login, logout, updateUser, refreshToken };
}
