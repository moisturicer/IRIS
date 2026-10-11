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

/**
 * Record pipeline statuses — match `PipelineStatus` in Django (`core/enums.py`).
 *
 * One value for a record in review, whoever holds it (ADR-021 §4). The fixed
 * pipeline's five stage values and the stored `declined` were migrated away by
 * IR-260 and removed by IR-274; a revision request is `workflow_state`
 * `awaiting_resubmission`, never a status. `lib/pipelineVocabulary.test.ts`
 * fails the build if one is read again.
 */
export const PIPELINE_STATUS = {
  DRAFT:          "draft",
  IN_REVIEW:      "in_review",
  // A Decision's outcomes (ADR-032 §2-§3)
  APPROVED:       "approved",       // a Proposal accepted by its Adviser, shown as Accepted; not public (IR-264)
  PUBLISHED:      "published",
  COMPLETED:      "completed",      // kept unlisted by RDCO, or a legacy Proposal the retired complete act finished
  REJECTED:       "rejected",       // terminal, shown as Archived
  PENDING_DELETE: "pending_delete",
} as const;

export type PipelineStatus = (typeof PIPELINE_STATUS)[keyof typeof PIPELINE_STATUS];

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
