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
