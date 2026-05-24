import { Navigate, Outlet } from "react-router-dom";
import type { RoleName } from "@/lib/constants";
import type { User } from "@/types/auth";
import { useAuthStore } from "@/store/auth.store";
import { decodeJwtPayload, isJwtExpired } from "@/lib/jwt";
import { ForbiddenScreen } from "./ForbiddenScreen";

interface ProtectedRouteProps {
  allowedRoles: RoleName[];
}

function resolveRoleName(token: string, user: User | null): RoleName | null {
  const payload = decodeJwtPayload(token);
  if (!payload) return null;

  if (payload.role_id != null && user?.role === payload.role_id && user.role_name) {
    return user.role_name;
  }

  return user?.role_name ?? null;
}

/**
 * Route guard — validates in-memory JWT and enforces client-side RBAC (UX only).
 * Real enforcement is on the Django API (NFR-S4).
 */
export function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const user        = useAuthStore((s) => s.user);

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  const payload = decodeJwtPayload(accessToken);
  if (!payload || isJwtExpired(payload)) {
    useAuthStore.getState().logout();
    return <Navigate to="/login" replace state={{ reason: "session_expired" }} />;
  }

  const roleName = resolveRoleName(accessToken, user);
  if (!roleName || !allowedRoles.includes(roleName)) {
    return (
      <ForbiddenScreen
        authenticatedRole={roleName ?? user?.role_name ?? null}
        requiredRoles={allowedRoles}
      />
    );
  }

  return <Outlet />;
}
