import { useAuthStore } from "@/store/auth.store";
import { ROLES, REVIEWER_ROLES, STAFF_ROLES, type RoleName } from "@/lib/constants";

export function useRole() {
  const user     = useAuthStore((s) => s.user);
  const roleName = user?.role_name ?? null;

  // Django staff/superuser accounts have no role but should have full access
  const isDjangoStaff = user?.is_staff === true || user?.is_superuser === true;

  return {
    roleName,
    isDjangoStaff,
    isStudent:  roleName === ROLES.STUDENT,
    isAdviser:  roleName === ROLES.ADVISER,
    isKTTO:     roleName === ROLES.KTTO,
    isRDCO:     roleName === ROLES.RDCO,
    isITSO:     roleName === ROLES.ITSO,
    isTBI:      roleName === ROLES.TBI,
    isIERC:     roleName === ROLES.IERC,
    isAdmin:    roleName === ROLES.ADMIN,
    isReviewer: isDjangoStaff || REVIEWER_ROLES.includes(roleName as RoleName),
    isStaff:    isDjangoStaff || STAFF_ROLES.includes(roleName as RoleName),
  };
}
