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
    ]

    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, db_index=True)
    user       = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="audit_events"
    )
    record     = models.ForeignKey(
        "records.Record", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_events"
    )
    # Store extra details without polluting the schema with more columns
    metadata   = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} | {self.user_id} | {self.created_at:%Y-%m-%d %H:%M}"
