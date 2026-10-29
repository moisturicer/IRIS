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
    SESSION_REVOKE   = "SESSION_REVOKE"
    QUESTION_INJECTION = "QUESTION_INJECTION"

    # Workflow events (IR-144): one type per act, written by the workflow
    # services inside the act's own transaction (`apps.audit.workflow`). Their
    # metadata keys are documented in docs/evaluation/AUDIT_EXPORT.md.
    SUBMITTED                  = "SUBMITTED"
    ROUTED                     = "ROUTED"
    ASSIGNMENT_CLOSED          = "ASSIGNMENT_CLOSED"
    ASSIGNMENT_EXTENDED        = "ASSIGNMENT_EXTENDED"
    DECISION_RECORDED          = "DECISION_RECORDED"
    PUBLISHED                  = "PUBLISHED"
    RESUBMISSION_REQUESTED     = "RESUBMISSION_REQUESTED"
    REVISION_REQUEST_WITHDRAWN = "REVISION_REQUEST_WITHDRAWN"
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
    DOCUMENT_REQUESTED         = "DOCUMENT_REQUESTED"
    DOCUMENT_REQUEST_FULFILLED = "DOCUMENT_REQUEST_FULFILLED"
    DOCUMENT_REQUEST_ACCEPTED  = "DOCUMENT_REQUEST_ACCEPTED"
    DOCUMENT_REQUEST_REJECTED  = "DOCUMENT_REQUEST_REJECTED"
    DOCUMENT_REQUEST_WITHDRAWN = "DOCUMENT_REQUEST_WITHDRAWN"

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
        (SESSION_REVOKE,   "Session Revoked"),
        (QUESTION_INJECTION, "Reader Question Injection Flagged"),
        (SUBMITTED,                  "Submitted"),
        (ROUTED,                     "Routed"),
        (ASSIGNMENT_CLOSED,          "Assignment Closed"),
        (ASSIGNMENT_EXTENDED,        "Assignment Deadline Extended"),
        (DECISION_RECORDED,          "Decision Recorded"),
        (PUBLISHED,                  "Published"),
        (RESUBMISSION_REQUESTED,     "Revision Requested"),
        (REVISION_REQUEST_WITHDRAWN, "Revision Request Withdrawn"),
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
        (DOCUMENT_REQUESTED,         "Documents Requested"),
        (DOCUMENT_REQUEST_FULFILLED, "Document Request Fulfilled"),
        (DOCUMENT_REQUEST_ACCEPTED,  "Requested Document Accepted"),
        (DOCUMENT_REQUEST_REJECTED,  "Requested Document Rejected"),
        (DOCUMENT_REQUEST_WITHDRAWN, "Document Request Withdrawn"),
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
