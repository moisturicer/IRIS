import { useAuthStore } from "@/store/auth.store";
import { ROLES, REVIEWER_ROLES, STAFF_ROLES, type RoleName } from "@/lib/constants";

export function useRole() {
  const roleName = useAuthStore((s) => s.user?.role_name ?? null);

  return {
    roleName,
    isStudent:  roleName === ROLES.STUDENT,
    isAdviser:  roleName === ROLES.ADVISER,
    isKTTO:     roleName === ROLES.KTTO,
    isRDCO:     roleName === ROLES.RDCO,
    isITSO:     roleName === ROLES.ITSO,
    isTBI:      roleName === ROLES.TBI,
    isReviewer: REVIEWER_ROLES.includes(roleName as RoleName),
    isStaff:    STAFF_ROLES.includes(roleName as RoleName),
  };
}
