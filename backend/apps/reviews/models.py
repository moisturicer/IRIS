from django.db import models


class Review(models.Model):
    """
    One row per review action on a record at a specific pipeline stage.
    Used for both sequential stages (adviser, rdco_intake, rdco) and
    parallel clearance stages (itso, ierc, ktto). The comment is embedded
    directly so you never need a second JOIN.
    """
    STAGE_CHOICES = [
        ("adviser",     "Adviser"),
        ("rdco_intake", "RDCO Intake"),
        ("itso",        "ITSO"),
        ("ierc",        "IERC"),
        ("ktto",        "KTTO"),
        ("rdco",        "RDCO Final"),
    ]
    STATUS_CHOICES = [
        ("approved",  "Approved"),
        ("declined",  "Declined"),   # revision requested; owner may resubmit
        ("rejected",  "Rejected"),   # terminal; owner cannot resubmit
    ]

    record      = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="reviews"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="reviews_given"
    )
    stage       = models.CharField(max_length=20, choices=STAGE_CHOICES, db_index=True)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, db_index=True)
    comment     = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.record_id} | {self.stage} | {self.status} by {self.reviewed_by_id}"


class RecordClearance(models.Model):
    """
    Tracks each reviewing office's individual clearance status for a record.
    Used during clearance stages (itso_review, parallel_review).

    Lifecycle:
      - Created by approve_record at rdco_intake (creates ITSO+KTTO for Project;
        IERC+KTTO for Thesis/Research).
      - For Project, the IERC clearance is created when ITSO clears (pipeline → parallel_review).
      - On resubmit after a clearance-office decline: only that office's row is reset to
        "pending"; other offices' clearance progress is preserved.
      - On resubmit after a sequential-stage decline: all rows are deleted for a clean restart.
    """
    OFFICE_CHOICES = [
        ("itso", "ITSO"),
        ("ierc", "IERC"),
        ("ktto", "KTTO"),
    ]
    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("cleared",  "Cleared"),
        ("declined", "Declined"),  # revision requested
        ("rejected", "Rejected"),  # terminal
    ]

    record      = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="clearances"
    )
    office      = models.CharField(max_length=10, choices=OFFICE_CHOICES)
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="clearances_given"
    )
    comment    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("record", "office")
        ordering        = ["record", "office"]

    def __str__(self):
        return f"Record {self.record_id} | {self.office} | {self.status}"


class RecordAuthPin(models.Model):
    """
    A one-time PIN emailed to a user to grant temporary access to a protected record.
    PINs expire 24 hours after generation and can only be used once.
    """
    record     = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="auth_pins")
    user       = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="auth_pins")
    email      = models.EmailField()
    pin        = models.CharField(max_length=6)
    is_used    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Pin for record {self.record_id} user {self.user_id}"
