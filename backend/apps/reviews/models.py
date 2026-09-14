from django.db import models

from core.enums import ClearanceStatus, Office, ReviewDecision, ReviewStage


class Review(models.Model):
    """
    One row per review action on a record at a specific pipeline stage.
    Used for both sequential stages (adviser, rdco_intake, rdco) and
    parallel clearance stages (itso, ierc, ktto). The comment is embedded
    directly so you never need a second JOIN.
    """
    #: Values live in core.enums (IR-135). `declined` requests a revision and
    #: the owner may resubmit; `rejected` is terminal.
    STAGE_CHOICES = ReviewStage.choices
    STATUS_CHOICES = ReviewDecision.choices

    record      = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="reviews"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="reviews_given"
    )
    stage       = models.CharField(max_length=20, choices=ReviewStage.choices, db_index=True)
    status      = models.CharField(max_length=20, choices=ReviewDecision.choices, db_index=True)
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
    #: Values live in core.enums (IR-135).
    OFFICE_CHOICES = Office.choices
    STATUS_CHOICES = ClearanceStatus.choices

    record      = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="clearances"
    )
    office      = models.CharField(max_length=10, choices=Office.choices)
    status      = models.CharField(
        max_length=10, choices=ClearanceStatus.choices, default=ClearanceStatus.PENDING
    )
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
