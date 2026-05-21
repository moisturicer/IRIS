from django.db import models


class Review(models.Model):
    """
    One row per review action (approve or decline) on a record at a specific pipeline stage.
    Replaces the old CheckedRecord + CheckedRecordComment pair.
    The comment is embedded directly so you never need a second JOIN.
    """
    STAGE_CHOICES = [
        ("adviser", "Adviser"),
        ("ktto",    "KTTO / TBI"),
        ("rdco",    "RDCO"),
    ]
    STATUS_CHOICES = [
        ("approved", "Approved"),
        ("declined", "Declined"),
    ]

    record      = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="reviews"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="reviews_given"
    )
    stage       = models.CharField(max_length=10, choices=STAGE_CHOICES, db_index=True)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    comment     = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        # Only one review per reviewer per stage per record
        unique_together = ("record", "reviewed_by", "stage")

    def __str__(self):
        return f"{self.record_id} | {self.stage} | {self.status} by {self.reviewed_by_id}"


class RecordAuthPin(models.Model):
    """
    A one-time PIN emailed to a user to grant temporary access to a protected record.
    TODO: add expiry -- pins should expire after e.g. 24 hours.
    """
    record     = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="auth_pins")
    user       = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="auth_pins")
    email      = models.EmailField()
    pin        = models.CharField(max_length=10)
    is_used    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # TODO: expires_at = models.DateTimeField()

    def __str__(self):
        return f"Pin for record {self.record_id} user {self.user_id}"
