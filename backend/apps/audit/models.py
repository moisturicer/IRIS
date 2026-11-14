from django.db import models


class AuditEvent(models.Model):
    """
    Unified audit log.
    Replaces the 6 separate event models (LoginEvent, RecordAccessEvent,
    UploadEvent, DownloadEvent, DeletedFileEvent, FileRenameEvent).

    The `metadata` JSONB field holds event-specific details
    (e.g. for RENAME: {"old_name": "...", "new_name": "..."}).
    Use the EVENT_TYPE constants below when creating events.
    """
    LOGIN            = "LOGIN"
    LOGOUT           = "LOGOUT"
    FAILED_LOGIN     = "FAILED_LOGIN"
    ACCESS           = "ACCESS"
    UPLOAD           = "UPLOAD"
    DOWNLOAD         = "DOWNLOAD"
    DELETE           = "DELETE"
    RENAME           = "RENAME"
    PIN_GENERATED    = "PIN_GENERATED"
    PIN_VERIFIED     = "PIN_VERIFIED"
    ROLE_CHANGE      = "ROLE_CHANGE"
    ACCOUNT_LOCKED   = "ACCOUNT_LOCKED"
    ACCOUNT_UNLOCKED = "ACCOUNT_UNLOCKED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    SESSION_REVOKE   = "SESSION_REVOKE"
    SYSTEM_SETTING_CHANGED = "SYSTEM_SETTING_CHANGED"
    QUESTION_INJECTION = "QUESTION_INJECTION"
    RESEARCH_METADATA_CORRECTED = "RESEARCH_METADATA_CORRECTED"
    # Download requests (ADR-048 decision 9, IR-688). Metadata: `request`, the
    # DownloadRequest id; a revocation adds `requested_by`, the reader's id.
    DOWNLOAD_REQUEST_CANCELLED = "DOWNLOAD_REQUEST_CANCELLED"
    DOWNLOAD_GRANT_REVOKED     = "DOWNLOAD_GRANT_REVOKED"

    # Workflow events (IR-144): one type per act, written by the workflow
    # services inside the act's own transaction (`apps.audit.workflow`). Their
    # metadata keys are documented in docs/evaluation/AUDIT_EXPORT.md.
    SUBMITTED                  = "SUBMITTED"
    ROUTED                     = "ROUTED"
    ASSIGNMENT_CLOSED          = "ASSIGNMENT_CLOSED"
    ASSIGNMENT_EXTENDED        = "ASSIGNMENT_EXTENDED"
    ASSIGNMENT_ESCALATED       = "ASSIGNMENT_ESCALATED"
    DECISION_RECORDED          = "DECISION_RECORDED"
    PUBLISHED                  = "PUBLISHED"
    RESUBMISSION_REQUESTED     = "RESUBMISSION_REQUESTED"
    REVISION_REQUEST_WITHDRAWN = "REVISION_REQUEST_WITHDRAWN"
    REVISION_DRAFT_DISCARDED   = "REVISION_DRAFT_DISCARDED"
    RESUBMITTED                = "RESUBMITTED"
    CLEARANCE_PRESERVED        = "CLEARANCE_PRESERVED"
    SEAT_CLAIMED               = "SEAT_CLAIMED"
    SEAT_ASSIGNED              = "SEAT_ASSIGNED"
    SEAT_NOMINATED             = "SEAT_NOMINATED"
    SEAT_REASSIGNED            = "SEAT_REASSIGNED"
    SEAT_WITHDRAWN             = "SEAT_WITHDRAWN"
    REVIEWER_ADDED             = "REVIEWER_ADDED"
    SEAT_OPENED                = "SEAT_OPENED"
    RECORD_WITHDRAWN           = "RECORD_WITHDRAWN"
    # RDCO's two other acts on a paper in review (ADR-051 §10, IR-797).
    ADVISER_REPLACED           = "ADVISER_REPLACED"
    OWNER_ADDED                = "OWNER_ADDED"
    CONTACT_PERSON_CHANGED     = "CONTACT_PERSON_CHANGED"
    DOCUMENT_REQUESTED         = "DOCUMENT_REQUESTED"
    DOCUMENT_REQUEST_FULFILLED = "DOCUMENT_REQUEST_FULFILLED"
    DOCUMENT_REQUEST_ACCEPTED  = "DOCUMENT_REQUEST_ACCEPTED"
    DOCUMENT_REQUEST_REJECTED  = "DOCUMENT_REQUEST_REJECTED"
    DOCUMENT_REQUEST_WITHDRAWN = "DOCUMENT_REQUEST_WITHDRAWN"
    # Review threads (ADR-032 §7, 2026-11-04; IR-874). No thread text is copied.
    REVIEW_FINISHED                = "REVIEW_FINISHED"
    REVIEW_THREAD_RESOLVED         = "REVIEW_THREAD_RESOLVED"
    REVIEW_THREAD_REOPENED         = "REVIEW_THREAD_REOPENED"
    REVIEW_THREAD_SEVERITY_CHANGED = "REVIEW_THREAD_SEVERITY_CHANGED"
    REVIEW_THREAD_ANSWERED         = "REVIEW_THREAD_ANSWERED"
    REVIEW_THREADS_CLOSED          = "REVIEW_THREADS_CLOSED"

    # A paper's embargo (ADR-052 §8, IR-812). Nothing writes EMBARGO_ANSWERED
    # since IR-882 removed Publish's question; it names the rows written before.
    EMBARGO_ANSWERED = "EMBARGO_ANSWERED"
    EMBARGO_SET      = "EMBARGO_SET"
    EMBARGO_EXTENDED = "EMBARGO_EXTENDED"
    EMBARGO_RELEASED = "EMBARGO_RELEASED"
    # KTTO's release of an IP-marked paper (ADR-052 §11, IR-813).
    IP_RELEASED      = "IP_RELEASED"

    # Account recovery (ADR-045 §8, IR-642). Metadata is an allowlist --
    # purpose, correlation_id, outcome, reason, attempt -- written only by
    # `apps.accounts.recovery.audit`. Never an address, token or password.
    RECOVERY_REQUESTED           = "RECOVERY_REQUESTED"
    RECOVERY_SUPPRESSED          = "RECOVERY_SUPPRESSED"
    RECOVERY_TOKEN_REJECTED      = "RECOVERY_TOKEN_REJECTED"
    RECOVERY_EMAIL_SENT          = "RECOVERY_EMAIL_SENT"
    RECOVERY_EMAIL_FAILED        = "RECOVERY_EMAIL_FAILED"
    PASSWORD_RESET_COMPLETED     = "PASSWORD_RESET_COMPLETED"
    EMAIL_VERIFICATION_COMPLETED = "EMAIL_VERIFICATION_COMPLETED"
    # The daily retention cleanup (ADR-051 decision 19, IR-794). No actor and no
    # record. Metadata: `counts`, the rows erased per data type -- never a name,
    # an email or any erased text.
    RETENTION_CLEANUP_RUN = "RETENTION_CLEANUP_RUN"

    # A person's answer to the data notice (ADR-054, IR-789). Metadata:
    # `notice_version`, `ai_consent`, and the `previous_*` pair (None when it was
    # their first answer). Written by `apps.accounts.notice.answer_notice`.
    NOTICE_ANSWERED = "NOTICE_ANSWERED"
    # RDCO published a new data notice version (ADR-051 decisions 16-17 as amended
    # by ADR-063 decision 9, IR-799). `user` is the publisher. Metadata:
    # `notice_version`, `previous_notice_version`, `characters` and `sha256` of
    # the text, never the text itself, which the version row holds.
    NOTICE_PUBLISHED = "NOTICE_PUBLISHED"
    # A person changed their own AI answer from Settings, or a Yes at a new notice
    # reached their earlier papers (ADR-054 decisions 11-13, IR-791). Metadata:
    # `previous_ai_consent`, `ai_consent`, `papers` (`all` or `from_now`, only
    # for a No becoming a Yes), `papers_updated` and `paper_ids`: ids and counts,
    # never a title. Written by `apps.accounts.ai_answer`.
    AI_ANSWER_CHANGED = "AI_ANSWER_CHANGED"
    # A person downloaded their own data (ADR-051 decision 13, IR-786). Metadata
    # is `sections` and `format` only: never a byte of what was downloaded.
    PERSONAL_DATA_EXPORTED = "PERSONAL_DATA_EXPORTED"

    # Unverified registrations (ADR-051 decisions 24-25, IR-705). REPLACED's
    # `user` is the earlier account, removed because its address registered
    # again, with empty metadata. EXPIRED is one per daily run, no actor, and
    # metadata `expired` and `skipped` counts: never a name or an address.
    REGISTRATION_REPLACED            = "REGISTRATION_REPLACED"
    UNVERIFIED_REGISTRATIONS_EXPIRED = "UNVERIFIED_REGISTRATIONS_EXPIRED"

    # RDCO's Setup (ADR-063 decision 11, IR-971). `user` is the RDCO account.
    # Metadata: `record_type` (id) and `record_type_name`; a requirement's
    # `slot` (id) and `name`; CHANGED's `changes` ({field: [before, after]},
    # descriptions as character counts, never their text); REORDERED's
    # `order` (slot ids); REMOVED's `outcome` (`hidden` or `deleted`); a
    # Template's `target` (`requirement` or `manuscript`), `filename` and
    # `bytes`. Downloads are not logged (decision 11).
    REQUIREMENT_ADDED     = "REQUIREMENT_ADDED"
    REQUIREMENT_CHANGED   = "REQUIREMENT_CHANGED"
    REQUIREMENTS_REORDERED = "REQUIREMENTS_REORDERED"
    REQUIREMENT_REMOVED   = "REQUIREMENT_REMOVED"
    TEMPLATE_REPLACED     = "TEMPLATE_REPLACED"
    TEMPLATE_REMOVED      = "TEMPLATE_REMOVED"
    RECORD_TYPE_DESCRIBED = "RECORD_TYPE_DESCRIBED"

    # Account deletion (ADR-051 §8-§12, IR-785)
    ACCOUNT_DELETION_REQUESTED = "ACCOUNT_DELETION_REQUESTED"
    ACCOUNT_DELETION_CANCELLED = "ACCOUNT_DELETION_CANCELLED"
    ACCOUNT_DELETION_CONFIRMED = "ACCOUNT_DELETION_CONFIRMED"
    ACCOUNT_DELETION_REJECTED  = "ACCOUNT_DELETION_REJECTED"

    EVENT_TYPE_CHOICES = [
        (LOGIN,            "Login"),
        (LOGOUT,           "Logout"),
        (FAILED_LOGIN,     "Failed Login"),
        (ACCESS,           "Record Access"),
        (UPLOAD,           "File Upload"),
        (DOWNLOAD,         "File Download"),
        (DELETE,           "File Delete"),
        (RENAME,           "File Rename"),
        (PIN_GENERATED,    "PIN Generated"),
        (PIN_VERIFIED,     "PIN Verified"),
        (ROLE_CHANGE,      "Role Change"),
        (ACCOUNT_LOCKED,   "Account Locked"),
        (ACCOUNT_UNLOCKED, "Account Unlocked"),
        (PASSWORD_CHANGED, "Password Changed"),
        (SESSION_REVOKE,   "Session Revoked"),
        (SYSTEM_SETTING_CHANGED, "System Setting Changed"),
        (QUESTION_INJECTION, "Reader Question Injection Flagged"),
        (RESEARCH_METADATA_CORRECTED, "Research Metadata Corrected"),
        (DOWNLOAD_REQUEST_CANCELLED, "Download Request Cancelled"),
        (DOWNLOAD_GRANT_REVOKED,     "Download Access Revoked"),
        (SUBMITTED,                  "Submitted"),
        (ROUTED,                     "Routed"),
        (ASSIGNMENT_CLOSED,          "Assignment Closed"),
        (ASSIGNMENT_EXTENDED,        "Assignment Deadline Extended"),
        (ASSIGNMENT_ESCALATED,       "Assignment Overdue Escalated"),
        (DECISION_RECORDED,          "Decision Recorded"),
        (PUBLISHED,                  "Published"),
        (RESUBMISSION_REQUESTED,     "Revision Requested"),
        (REVISION_REQUEST_WITHDRAWN, "Revision Request Withdrawn"),
        (REVISION_DRAFT_DISCARDED,   "Revised Manuscript Discarded"),
        (RESUBMITTED,                "New Version Submitted"),
        (CLEARANCE_PRESERVED,        "Clearance Preserved"),
        (SEAT_CLAIMED,               "Seat Claimed"),
        (SEAT_ASSIGNED,              "Seat Assigned"),
        (SEAT_NOMINATED,             "Seat Nominated"),
        (SEAT_REASSIGNED,            "Seat Reassigned"),
        (SEAT_WITHDRAWN,             "Seat Withdrawn"),
        (REVIEWER_ADDED,             "Reviewer Added"),
        (SEAT_OPENED,                "Seat Opened"),
        (RECORD_WITHDRAWN,           "Record Withdrawn"),
        (ADVISER_REPLACED,           "Adviser Replaced"),
        (OWNER_ADDED,                "Owner Added"),
        (CONTACT_PERSON_CHANGED,     "Contact Person Changed"),
        (EMBARGO_ANSWERED,           "Embargo Question Answered"),
        (EMBARGO_SET,                "Embargo Set"),
        (EMBARGO_EXTENDED,           "Embargo Date Moved"),
        (EMBARGO_RELEASED,           "Embargo Released"),
        (IP_RELEASED,                "IP Mark Released"),
        (DOCUMENT_REQUESTED,         "Documents Requested"),
        (DOCUMENT_REQUEST_FULFILLED, "Document Request Fulfilled"),
        (DOCUMENT_REQUEST_ACCEPTED,  "Requested Document Accepted"),
        (DOCUMENT_REQUEST_REJECTED,  "Requested Document Rejected"),
        (DOCUMENT_REQUEST_WITHDRAWN, "Document Request Withdrawn"),
        (REVIEW_FINISHED,                "Review Finished"),
        (REVIEW_THREAD_RESOLVED,         "Review Thread Resolved"),
        (REVIEW_THREAD_REOPENED,         "Review Thread Reopened"),
        (REVIEW_THREAD_SEVERITY_CHANGED, "Review Thread Severity Changed"),
        (REVIEW_THREAD_ANSWERED,         "Review Thread Answered"),
        (REVIEW_THREADS_CLOSED,          "Review Threads Closed by Decision"),
        (RECOVERY_REQUESTED,           "Recovery Requested"),
        (RECOVERY_SUPPRESSED,          "Recovery Suppressed"),
        (RECOVERY_TOKEN_REJECTED,      "Recovery Link Rejected"),
        (RECOVERY_EMAIL_SENT,          "Recovery Email Sent"),
        (RECOVERY_EMAIL_FAILED,        "Recovery Email Failed"),
        (PASSWORD_RESET_COMPLETED,     "Password Reset Completed"),
        (EMAIL_VERIFICATION_COMPLETED, "Email Verification Completed"),
        (ACCOUNT_DELETION_REQUESTED, "Account Deletion Requested"),
        (ACCOUNT_DELETION_CANCELLED, "Account Deletion Cancelled"),
        (ACCOUNT_DELETION_CONFIRMED, "Account Deleted"),
        (ACCOUNT_DELETION_REJECTED,  "Account Deletion Rejected"),
        (RETENTION_CLEANUP_RUN,        "Retention Cleanup Run"),
        (REGISTRATION_REPLACED,            "Registration Replaced"),
        (UNVERIFIED_REGISTRATIONS_EXPIRED, "Unverified Registrations Expired"),
        (NOTICE_ANSWERED,              "Data Notice Answered"),
        (NOTICE_PUBLISHED,             "Data Notice Published"),
        (AI_ANSWER_CHANGED,            "AI Answer Changed"),
        (PERSONAL_DATA_EXPORTED,       "Personal Data Downloaded"),
        (REQUIREMENT_ADDED,            "Requirement Added"),
        (REQUIREMENT_CHANGED,          "Requirement Changed"),
        (REQUIREMENTS_REORDERED,       "Requirements Reordered"),
        (REQUIREMENT_REMOVED,          "Requirement Removed"),
        (TEMPLATE_REPLACED,            "Template Replaced"),
        (TEMPLATE_REMOVED,             "Template Removed"),
        (RECORD_TYPE_DESCRIBED,        "Record Type Description Changed"),
    ]

    event_type = models.CharField(max_length=40, choices=EVENT_TYPE_CHOICES, db_index=True)
    # DO_NOTHING with no database constraint (IR-166): deleting a User or a
    # Record must not touch its audit rows, which are insert-only at the
    # database. The row keeps the deleted subject's id; `select_related` reads
    # it as None. SET_NULL would have needed an UPDATE the trigger allowed, and
    # that exception let anyone strip attribution from the whole log.
    user       = models.ForeignKey(
        "accounts.User", on_delete=models.DO_NOTHING, db_constraint=False, null=True,
        related_name="audit_events"
    )
    record     = models.ForeignKey(
        "records.Record", on_delete=models.DO_NOTHING, db_constraint=False, null=True, blank=True,
        related_name="audit_events"
    )
    # Store extra details without polluting the schema with more columns
    metadata   = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} | {self.user_id} | {self.created_at:%Y-%m-%d %H:%M}"
