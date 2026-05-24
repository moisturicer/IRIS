/** Role names — must match `Role.name` in the Django database exactly. */
export const ROLES = {
  STUDENT: "Student",
  ADVISER: "Adviser",
  KTTO:    "KTTO",
  RDCO:    "RDCO",
  ITSO:    "ITSO",
  TBI:     "TBI",
} as const;

export type RoleName = (typeof ROLES)[keyof typeof ROLES];

export const REVIEWER_ROLES: RoleName[] = [
  ROLES.ADVISER,
  ROLES.KTTO,
  ROLES.RDCO,
  ROLES.TBI,
];

export const STAFF_ROLES: RoleName[] = [
  ROLES.KTTO,
  ROLES.RDCO,
  ROLES.ITSO,
  ROLES.TBI,
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

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
