import type { RoleName } from "@/lib/constants";

/** SRS-style diagnostic codes shown on the 403 page. */
const ROLE_DIAGNOSTIC: Record<RoleName | string, string> = {
  Student: "STUDENT",
  Adviser: "ADVISER",
  KTTO:    "KTTO",
  RDCO:    "RDCO_DIRECTOR",
  ITSO:    "ITSO",
  IERC:    "IERC",
};

export function roleToDiagnosticCode(role: string | null | undefined): string {
  if (!role) return "UNKNOWN";
  return ROLE_DIAGNOSTIC[role] ?? role.replace(/\s+/g, "_").toUpperCase();
}
