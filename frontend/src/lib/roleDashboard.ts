import { ROLES, type RoleName } from "@/lib/constants";

/** Default landing route after login for each role. */
export function getRoleDashboardPath(roleName: RoleName | null | undefined): string {
  switch (roleName) {
    case ROLES.STUDENT:
      return "/";
    case ROLES.ADVISER:
    case ROLES.KTTO:
    case ROLES.RDCO:
    case ROLES.IERC:
      return "/review/pending";
    case ROLES.ITSO:
      return "/records";
    default:
      return "/";
  }
}