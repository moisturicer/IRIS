/** Role names — must match `Role.name` in the Django database exactly. */
export const ROLES = {
  STUDENT: "Student",
  ADVISER: "Adviser",
  KTTO:    "KTTO",
  RDCO:    "RDCO",
  ITSO:    "ITSO",
  IERC:    "IERC",
} as const;

export type RoleName = (typeof ROLES)[keyof typeof ROLES];

/** Every defined role — use as the default `allowedRoles` for any authenticated route. */
export const ALL_ROLES: RoleName[] = Object.values(ROLES);

export const REVIEWER_ROLES: RoleName[] = [
  ROLES.ADVISER,
  ROLES.KTTO,
  ROLES.RDCO,
  ROLES.ITSO,
  ROLES.IERC,
];

export const STAFF_ROLES: RoleName[] = [
  ROLES.KTTO,
  ROLES.RDCO,
  ROLES.ITSO,
  ROLES.IERC,
];

export const REQUEST_QUEUE_ROLES: RoleName[] = [
  ROLES.KTTO,
  ROLES.RDCO,
];

export const AUDIT_LOG_ROLES: RoleName[] = [
  ROLES.RDCO,
];

/** Record pipeline statuses — match `Record.PIPELINE_STATUS` in Django. */
export const PIPELINE_STATUS = {
  DRAFT:          "draft",
  // The one in-review status IR-260 stores in place of the stage values below
  // (ADR-021 §4). Mirrors `PipelineStatus.IN_REVIEW`, added by IR-256.
  IN_REVIEW:      "in_review",
  // Proposal pipeline
  ADVISER_REVIEW: "adviser_review",
  APPROVED:       "approved",       // Proposal approved by adviser — research ongoing; not public (IR-264)
  // Thesis/Research and Project pipeline
  RDCO_INTAKE:      "rdco_intake",
  ITSO_REVIEW:      "itso_review",
  PARALLEL_REVIEW:  "parallel_review",
  RDCO_REVIEW:      "rdco_review",
  // Terminal / visible states
  PUBLISHED:      "published",
  DECLINED:       "declined",       // sent back for revision; owner may resubmit
  REJECTED:       "rejected",       // outright rejection; no resubmission
  PENDING_DELETE: "pending_delete",
  COMPLETED:      "completed",      // Proposal research finished — marked by RDCO or the assigned Adviser
} as const;

export type PipelineStatus = (typeof PIPELINE_STATUS)[keyof typeof PIPELINE_STATUS];

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
