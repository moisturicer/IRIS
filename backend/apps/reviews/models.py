from django.db import models
from django.utils import timezone

from core.enums import (
    ASSIGNABLE_PARTIES,
    AssignmentState,
    ClearanceStatus,
    Office,
    ResubmissionRequestState,
    ReviewDecision,
    ReviewStage,
)

PARTY_CHOICES = [(p.value, p.label) for p in ASSIGNABLE_PARTIES]


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
    #: The assignment this review was made under (ADR-021 §8). Null on every
    #: review written before IR-257 starts dual-writing, and IR-257's backfill
    #: does not invent one for them.
    assignment  = models.ForeignKey(
        "reviews.RecordAssignment", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviews",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.record_id} | {self.stage} | {self.status} by {self.reviewed_by_id}"


class RecordClearance(models.Model):
    """
    Tracks each reviewing office's individual clearance status for a record.
    Used during clearance stages (itso_review, parallel_review).

    Lifecycle:
      - Created by approve_record at rdco_intake, one row per office the record
        requested (ADR-018; ITSO for either type since IR-266).
      - When ITSO was requested, the record waits at itso_review and IERC only
        joins once ITSO clears (pipeline → parallel_review).
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
    #: 20, not 10: `not_cleared` is 11 characters (IR-256).
    status      = models.CharField(
        max_length=20, choices=ClearanceStatus.choices, default=ClearanceStatus.PENDING
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


# ---------------------------------------------------------------------------
# Reviewer-directed routing (ADR-021 §8, IR-256)
#
# Added beside the current pipeline and written by nothing yet: IR-257
# dual-writes them, and IR-260 makes them authoritative. Three rules hold for
# all three tables (`docs/workflow_routing_architecture.md` §5):
#
# - **No workflow action deletes from them.** Closing an assignment or resolving
#   a request changes its `state`; the row is the history.
# - **No outcome is stored here.** Outcomes stay in `Review` and `RecordClearance`.
# - **No column stores `workflow_state`.** It is derived (ADR-021 §4).
#
# User foreign keys are `SET_NULL`: deleting an account must not delete the
# record of who routed, held or asked for what. Timestamps take a default
# rather than `auto_now_add`, because IR-257's backfill dates rows from the
# review history they reconstruct.
# ---------------------------------------------------------------------------

class RecordAssignment(models.Model):
    """
    One party's turn at acting on a record. ADR-021 §6 and §8.

    Several parties can hold a record at once. A party can hold it again after
    its earlier assignment closed, but never twice at the same time.
    """

    record    = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="assignments"
    )
    party     = models.CharField(max_length=20, choices=PARTY_CHOICES)
    state     = models.CharField(
        max_length=20, choices=AssignmentState.choices,
        default=AssignmentState.ACTIVE, db_index=True,
    )
    #: Null when the assignment was opened by submission or by the system.
    opened_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assignments_opened",
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assignments_closed",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    reason    = models.TextField(blank=True)

    class Meta:
        ordering = ["record", "opened_at"]
        constraints = [
            # ADR-021 §8: at most one active row per (record, party). Partial,
            # so every closed assignment for that party is still kept.
            models.UniqueConstraint(
                fields=["record", "party"],
                condition=models.Q(state=AssignmentState.ACTIVE),
                name="one_active_assignment_per_record_party",
            ),
        ]

    def __str__(self):
        return f"Record {self.record_id} | {self.party} | {self.state}"


class RoutingEvent(models.Model):
    """
    One party sending a record to another. ADR-021 §6.

    A `route()` call to several parties writes one event per target, and every
    event from that call shares a `group_id`, so "Intake -> ITSO + IERC" reads
    as one decision. The first events whose `from_party` is `intake` are the
    record's initial routing.
    """

    record     = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="routing_events"
    )
    actor      = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="routing_events",
    )
    #: Null when the submitter sent the record in, rather than a party.
    from_party = models.CharField(
        max_length=20, choices=PARTY_CHOICES, null=True, blank=True
    )
    to_party   = models.CharField(max_length=20, choices=PARTY_CHOICES)
    reason     = models.TextField(blank=True)
    #: No default. The caller that routes to several parties must supply one
    #: shared value, and a default would silently split such a call apart.
    group_id   = models.UUIDField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["record", "created_at"]
        indexes  = [models.Index(fields=["record", "created_at"])]

    def __str__(self):
        source = self.from_party or "submitter"
        return f"Record {self.record_id} | {source} -> {self.to_party}"


class ResubmissionRequest(models.Model):
    """
    One party asking the submitter for changes. ADR-021 §11.

    Replaces the stored `declined` status, which could not say that two parties
    are each waiting on a revision. Resubmitting resolves every open request.
    """

    record       = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="resubmission_requests"
    )
    party        = models.CharField(max_length=20, choices=PARTY_CHOICES)
    assignment   = models.ForeignKey(
        RecordAssignment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="resubmission_requests",
    )
    #: The `declined` review that carries the request's comment. `RESTRICT`,
    #: not `CASCADE`: deleting that review alone must not quietly delete the
    #: request history. Deleting the whole Record still removes both.
    review       = models.ForeignKey(
        Review, on_delete=models.RESTRICT, related_name="resubmission_requests"
    )
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="resubmission_requests_made",
    )
    reason       = models.TextField(blank=True)
    state        = models.CharField(
        max_length=20, choices=ResubmissionRequestState.choices,
        default=ResubmissionRequestState.OPEN,
    )
    created_at   = models.DateTimeField(default=timezone.now)
    resolved_by  = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="resubmission_requests_resolved",
    )
    resolved_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["record", "created_at"]
        indexes  = [models.Index(fields=["record", "state"])]

    def __str__(self):
        return f"Record {self.record_id} | {self.party} | {self.state}"


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
