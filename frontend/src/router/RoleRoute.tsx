import { Navigate, Outlet } from "react-router-dom";
import type { RoleName } from "@/lib/constants";
import { useRole } from "@/hooks/useRole";

interface RoleRouteProps {
  allowed: RoleName[];
}

/**
 * Renders children only if the current user's role is in the allowed list.
 * Otherwise renders a 403 page.
 * Usage: <RoleRoute allowed={[ROLES.KTTO, ROLES.RDCO]} />
 */
export function RoleRoute({ allowed }: RoleRouteProps) {
  const { roleName } = useRole();
  if (!roleName || !allowed.includes(roleName)) {
    // TODO: replace Navigate with a proper 403 page component
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}
