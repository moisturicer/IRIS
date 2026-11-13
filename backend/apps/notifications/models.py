from django.db import models


class NotificationType(models.Model):
    """
    Seed data:
      1  Role Request - Student
      2  Role Request - Adviser
      3  New Record (Proposal / Thesis)
      4  New Record (Project)
      5  Record Resubmission
      6  Role Request Approved
      7  Delete Request Submitted
      8  Delete Request Approved
      9  Download Request Submitted
      10 Download Request Approved
    """
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name


class TaskKind(models.TextChoices):
    """
    What a notification that asks for action is bound to (ADR-069). The id
    names one row of that kind, and `apps.notifications.settling` decides
    when that row's task has ended.
    """

    ASSIGNMENT = "assignment", "An office's (or the Adviser's) turn at a record"
    SEAT = "seat", "One reviewer's seat"
    REVISION = "revision", "A revision request"
    DOCUMENT_REQUEST = "document_request", "A document request"
    DOWNLOAD_REQUEST = "download_request", "A download request"
    DELETE_REQUEST = "delete_request", "A delete request"
    ROLE_REQUEST = "role_request", "A role request"


class NotificationQuerySet(models.QuerySet):

    def visible_to(self, user):
        """
        The notifications `user` may see and mark read: those sent to them,
        and broadcasts to their role (IR-300). The one scope the list,
        mark-read and mark-all-read endpoints share.

        A user with no role gets no broadcasts. Filtering on
        `broadcast_to_role=None` would match `IS NULL`, which is every direct
        notification in the system.
        """
        scope = models.Q(recipient=user)
        if user.role_id is not None:
            scope |= models.Q(broadcast_to_role_id=user.role_id)
        return self.filter(scope)


class Notification(models.Model):
    """
    A notification can be direct (recipient is set) or a broadcast to a role
    (broadcast_to_role is set, recipient is null).

    For broadcasts, every user with that role sees it.
    Per-user read state is tracked in NotificationRead.
    For direct notifications, read state is also tracked in NotificationRead
    (single row) -- this keeps the query logic uniform.
    """
    sender           = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sent_notifications"
    )
    # Direct recipient -- null if this is a broadcast
    recipient        = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, null=True, blank=True,
        related_name="direct_notifications"
    )
    # Broadcast target role -- null if this is a direct notification
    broadcast_to_role = models.ForeignKey(
        "accounts.Role", on_delete=models.CASCADE, null=True, blank=True,
        related_name="broadcast_notifications"
    )
    record           = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, null=True, blank=True,
        related_name="notifications"
    )
    notif_type       = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    message          = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    # --- The task this notification asked for (ADR-069, IR-1075) -------------
    # Only a notification that asks its recipient to act is bound to a task.
    # An informational one (a decision, a publication, a comment) leaves both
    # blank and never resolves.
    task_kind        = models.CharField(
        max_length=20, choices=TaskKind.choices, blank=True, default=""
    )
    task_id          = models.PositiveBigIntegerField(null=True, blank=True)
    # Set once, when the task ends, and never cleared: a clearance reset sends
    # a NEW notification instead of reopening this one (ADR-069 decision 5).
    resolved_at      = models.DateTimeField(null=True, blank=True)
    resolved_label   = models.CharField(max_length=200, blank=True, default="")

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notif_type.name} | {self.created_at:%Y-%m-%d}"


class NotificationRead(models.Model):
    """
    Tracks whether a specific user has read a specific notification.
    Works for both direct and broadcast notifications.
    """
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="reads")
    user         = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notification_reads")
    read_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("notification", "user")
