/** Role names — must match `Role.name` in the Django database exactly. */
export const ROLES = {
  STUDENT: "Student",
  ADVISER: "Adviser",
  KTTO:    "KTTO",
  RDCO:    "RDCO",
  ITSO:    "ITSO",
  TBI:     "TBI",
  IERC:    "IERC",
  ADMIN:   "System Administrator",
} as const;

export type RoleName = (typeof ROLES)[keyof typeof ROLES];

/** Every defined role — use as the default `allowedRoles` for any authenticated route. */
export const ALL_ROLES: RoleName[] = Object.values(ROLES);

export const REVIEWER_ROLES: RoleName[] = [
  ROLES.ADVISER,
  ROLES.KTTO,
  ROLES.RDCO,
  ROLES.TBI,
  ROLES.IERC,
];

export const APPROVAL_CHAIN_ROLES: RoleName[] = [
  ROLES.ADVISER,
  ROLES.KTTO,
  ROLES.TBI,
  ROLES.IERC,
  ROLES.RDCO,
];

export const STAFF_ROLES: RoleName[] = [
  ROLES.KTTO,
  ROLES.RDCO,
  ROLES.ITSO,
  ROLES.TBI,
];

export const REQUEST_QUEUE_ROLES: RoleName[] = [
  ROLES.KTTO,
  ROLES.TBI,
  ROLES.RDCO,
];

export const AUDIT_LOG_ROLES: RoleName[] = [
  ROLES.ADMIN,
  ROLES.RDCO,
];

/** Record pipeline statuses — match `Record.PIPELINE_STATUS` in Django. */
export const PIPELINE_STATUS = {
  DRAFT:          "draft",
  ADVISER_REVIEW: "adviser_review",
  KTTO_REVIEW:    "ktto_review",
  RDCO_REVIEW:    "rdco_review",
  PUBLISHED:      "published",
  DECLINED:       "declined",
  PENDING_DELETE: "pending_delete",
} as const;

export type PipelineStatus = (typeof PIPELINE_STATUS)[keyof typeof PIPELINE_STATUS];

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
