import { Outlet } from "react-router-dom";
import type { RoleName } from "@/lib/constants";
import { useRole } from "@/hooks/useRole";
import { ForbiddenPage } from "@/features/errors/ForbiddenPage";

interface RoleRouteProps {
  allowed: RoleName[];
}

/**
 * Renders child routes only if the current user's role is allowed.
 * Otherwise shows the 403 forbidden page (FR-M6-03).
 */
export function RoleRoute({ allowed }: RoleRouteProps) {
  const { roleName } = useRole();

  if (!roleName || !allowed.includes(roleName)) {
    return <ForbiddenPage requiredRoles={allowed} />;
  }

  return <Outlet />;
}
