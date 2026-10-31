export const AUDIT_EVENT_GROUPS = {
  Account: {
    LOGIN: "Login", LOGOUT: "Logout", FAILED_LOGIN: "Failed Login",
    PIN_GENERATED: "PIN Generated", PIN_VERIFIED: "PIN Verified", ROLE_CHANGE: "Role Change",
    ACCOUNT_LOCKED: "Account Locked", ACCOUNT_UNLOCKED: "Account Unlocked", SESSION_REVOKE: "Session Revoked",
    PASSWORD_CHANGED: "Password Changed",
  },
  Files: { ACCESS: "Record Access", UPLOAD: "File Upload", DOWNLOAD: "File Download", DELETE: "File Delete", RENAME: "File Rename" },
  Research: { RESEARCH_METADATA_CORRECTED: "Research Metadata Corrected" },
  Workflow: {
    SUBMITTED: "Submitted", ROUTED: "Routed", ASSIGNMENT_CLOSED: "Assignment Closed",
    ASSIGNMENT_EXTENDED: "Assignment Deadline Extended", DECISION_RECORDED: "Decision Recorded",
    ASSIGNMENT_ESCALATED: "Assignment Overdue Escalated",
    PUBLISHED: "Published", RESUBMISSION_REQUESTED: "Revision Requested",
    REVISION_REQUEST_WITHDRAWN: "Revision Request Withdrawn", RESUBMITTED: "New Version Submitted",
    CLEARANCE_PRESERVED: "Clearance Preserved", RECORD_WITHDRAWN: "Record Withdrawn",
  },
  "Document requests": {
    DOCUMENT_REQUESTED: "Documents Requested", DOCUMENT_REQUEST_FULFILLED: "Document Request Fulfilled",
    DOCUMENT_REQUEST_ACCEPTED: "Requested Document Accepted", DOCUMENT_REQUEST_REJECTED: "Requested Document Rejected",
    DOCUMENT_REQUEST_WITHDRAWN: "Document Request Withdrawn",
  },
  Seats: {
    SEAT_CLAIMED: "Seat Claimed", SEAT_ASSIGNED: "Seat Assigned", SEAT_NOMINATED: "Seat Nominated",
    SEAT_REASSIGNED: "Seat Reassigned", SEAT_WITHDRAWN: "Seat Withdrawn",
    REVIEWER_ADDED: "Reviewer Added", SEAT_OPENED: "Seat Opened",
  },
  "Ask IRIS": { QUESTION_INJECTION: "Reader Question Injection Flagged" },
} as const;

type Groups = typeof AUDIT_EVENT_GROUPS;
export type AuditEventType = { [K in keyof Groups]: keyof Groups[K] }[keyof Groups];
export const AUDIT_EVENT_LABELS: Record<AuditEventType, string> = Object.assign({}, ...Object.values(AUDIT_EVENT_GROUPS));

export interface AuditEvent {
  id:            number;
  event_type:    AuditEventType;
  user:          number | null;
  user_name:     string | null;
  record:        number | null;
  record_title:  string | null;
  metadata:      Record<string, unknown>;
  created_at:    string;
}
