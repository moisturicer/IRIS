import { useAuthStore } from "@/store/auth.store";

export function useAuth() {
  const { user, isAuthenticated, login, logout, updateUser } = useAuthStore();
  return { user, isAuthenticated, login, logout, updateUser };
}
