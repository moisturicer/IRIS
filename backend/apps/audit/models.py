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
    LOGIN                = "LOGIN"
    LOGOUT               = "LOGOUT"
    ACCESS               = "ACCESS"
    UPLOAD               = "UPLOAD"
    DOWNLOAD             = "DOWNLOAD"
    DELETE               = "DELETE"
    RENAME               = "RENAME"
    UNAUTHORIZED_ACCESS   = "UNAUTHORIZED_ACCESS"

    EVENT_TYPE_CHOICES = [
        (LOGIN,               "Login"),
        (LOGOUT,              "Logout"),
        (ACCESS,              "Record Access"),
        (UPLOAD,              "File Upload"),
        (DOWNLOAD,            "File Download"),
        (DELETE,              "File Delete"),
        (RENAME,              "File Rename"),
        (UNAUTHORIZED_ACCESS, "Unauthorized Access Attempt"),
    ]

    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES, db_index=True)
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
