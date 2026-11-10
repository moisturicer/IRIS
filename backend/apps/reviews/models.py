from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from core.enums import (
    RETIRED_PARTIES,
    AssignmentState,
    ClearanceStatus,
    Office,
    Party,
    ResubmissionRequestState,
    ReviewDecision,
    ReviewStage,
    ReviewVerdict,
    SeatSource,
    SeatState,
    ThreadAnswer,
    ThreadEventKind,
    ThreadPlaceOutcome,
    ThreadSeverity,
    ThreadState,
)

#: Every party, the retired Intake included: these columns hold history, and
#: an old row must stay readable. What may be newly assigned is
#: `core.enums.ASSIGNABLE_PARTIES`, enforced for assignments below.
PARTY_CHOICES = Party.choices


class Review(models.Model):
    """
    One reviewer's verdict on a record, as the party they reviewed for
    (`stage`: adviser, itso, ierc, ktto, rdco, or the retired intake on old
    rows). The comment is embedded directly so you never need a second JOIN.
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
    #: The record's Version this review was made against (ADR-032 §5, IR-416):
    #: its latest when the review was written. Null on every review written
    #: before IR-416, and the backfill does not date one against a version.
    version     = models.ForeignKey(
        "records.RecordVersion", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="reviews",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.record_id} | {self.stage} | {self.status} by {self.reviewed_by_id}"


class RecordClearance(models.Model):
    """
    One specialist office's clearance of a record (ITSO, IERC, KTTO).

    Lifecycle (ADR-032 §4):
      - Created when the record is first routed to the office.
      - Settled when the office's review round completes: `cleared` or
        `not_cleared`. A withdrawn round leaves it as it was.
      - On a new version under the clearance-aware policy, only the requesting
        office's row resets to `pending`; every other office's completed
        clearance is preserved (ADR-003). `RESTART_ALL` resets every row
        (ADR-004). Nothing is deleted.
      - Older rows may hold `declined` or `rejected`, written by the retired
        fixed pipeline.
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
    # ADR-043: old assignments deliberately stay undated. Configuration is
    # sampled once at opening, never on an ordinary save.
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    original_due_at = models.DateTimeField(null=True, blank=True)
    clock_started_at = models.DateTimeField(null=True, blank=True)
    document_pause_started_at = models.DateTimeField(null=True, blank=True)
    #: The Decision that closed this assignment: the decider's own, which
    #: completed, or another party's, which it withdrew (ADR-021 §12, IR-270).
    #: Null for anything closed another way.
    closed_by_decision = models.ForeignKey(
        "reviews.Review", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="closed_assignments",
    )

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
            # ADR-032 §13: a retired party is history only. Its closed rows
            # stay; an active one can never be written again (IR-274).
            models.CheckConstraint(
                condition=~models.Q(
                    state=AssignmentState.ACTIVE,
                    party__in=[p.value for p in RETIRED_PARTIES],
                ),
                name="no_active_assignment_for_a_retired_party",
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.state == AssignmentState.ACTIVE:
            from .deadlines import start_clock

            start_clock(self, self.opened_at)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Record {self.record_id} | {self.party} | {self.state}"


class Turnaround(models.Model):
    """Institution-entered working days; absence means no clock (ADR-043 §2)."""

    party = models.CharField(max_length=20, choices=[
        (p.value, p.label) for p in Party if p not in RETIRED_PARTIES
    ], unique=True)
    working_days = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.get_party_display()}: {self.working_days} working days"


class Holiday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}: {self.name}"


class Extension(models.Model):
    """Append-only history of a manual or document-pause date movement."""

    assignment = models.ForeignKey(RecordAssignment, on_delete=models.CASCADE,
                                   related_name="extensions")
    previous_due_at = models.DateTimeField()
    due_at = models.DateTimeField()
    reason = models.TextField()
    system = models.BooleanField(default=False)
    actor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL,
                              null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [models.CheckConstraint(
            condition=models.Q(due_at__gt=models.F("previous_due_at")),
            name="extension_moves_deadline_later",
        )]


class DeadlineMoment(models.Model):
    """
    A reminder or escalation already sent for one due date (ADR-043 §8).

    The unique constraint is the idempotency: a re-run, a missed tick or two
    beat instances insert the same row, and only one insert wins. A new due
    date is a new key, which is how an Extension or a pause re-arms every
    moment. `step` counts the repeat escalations every 5 working days (§7);
    it is 0 for both reminders.
    """

    class Kind(models.TextChoices):
        DUE_SOON = "due_soon", "Due in 2 working days"
        DUE_TODAY = "due_today", "Due today"
        ESCALATION = "escalation", "Overdue escalation"

    assignment = models.ForeignKey(RecordAssignment, on_delete=models.CASCADE,
                                   related_name="deadline_moments")
    due_at = models.DateTimeField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    step = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["sent_at", "pk"]
        constraints = [models.UniqueConstraint(
            fields=["assignment", "due_at", "kind", "step"],
            name="one_deadline_moment_per_due_date",
        )]


class ReviewerSeat(models.Model):
    """
    One person reviewing a record for a party. ADR-032 §4, IR-415.

    The assignment says "this office has the record"; the seat says "this
    person is reviewing it for that office". An active assignment with no
    seat is the office's **pool**: routed there, and claimed by nobody yet.
    An assignment can hold several seats, so two ITSO members can both review.

    The IR-256 rules hold here too: no workflow action deletes a seat (a
    withdrawal changes its `state`), and a seat stores no verdict -- that is
    the holder's `Review`.
    """

    assignment  = models.ForeignKey(
        RecordAssignment, on_delete=models.CASCADE, related_name="seats"
    )
    #: `SET_NULL`, like every user foreign key on these tables: deleting an
    #: account must not delete the history of who reviewed what.
    reviewer    = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviewer_seats",
    )
    state       = models.CharField(
        max_length=20, choices=SeatState.choices, default=SeatState.ASSIGNED,
    )
    source      = models.CharField(max_length=20, choices=SeatSource.choices)
    #: Who seated the reviewer: the coordinator, the router, the colleague who
    #: added them, or the claimer themselves. Null for an entry seat and a
    #: backfilled one, which nobody chose.
    assigned_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviewer_seats_assigned",
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    #: Stamped by *Open review* (§4): the time-on-task start IR-144 measures from.
    opened_at   = models.DateTimeField(null=True, blank=True)
    done_at     = models.DateTimeField(null=True, blank=True)
    #: The Decision that withdrew this seat while it was still open (IR-270),
    #: which is how the tracker tells it from a seat a coordinator withdrew.
    closed_by_decision = models.ForeignKey(
        "reviews.Review", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="closed_seats",
    )
    #: The seat a coordinator's *Reassign* moved this one from, and why
    #: (IR-623). Blank on every seat that was not reassigned.
    reassigned_from = models.ForeignKey(
        "self", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reassigned_to",
    )
    reason      = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["assignment", "assigned_at", "pk"]
        constraints = [
            # ADR-032 §4: at most one non-withdrawn seat per (assignment,
            # reviewer). Partial, so a withdrawn seat stays as history and the
            # same person can be seated again.
            models.UniqueConstraint(
                fields=["assignment", "reviewer"],
                condition=~models.Q(state=SeatState.WITHDRAWN),
                name="one_live_seat_per_assignment_reviewer",
            ),
        ]
        # My Reviews (IR-268) lists a user's seats by state.
        indexes = [models.Index(fields=["reviewer", "state"])]

    def __str__(self):
        return f"Assignment {self.assignment_id} | {self.reviewer_id} | {self.state}"


class RoutingEvent(models.Model):
    """
    One party sending a record to another. ADR-021 §6.

    A `route()` call to several parties writes one event per target, and every
    event from that call shares a `group_id`, so "Adviser -> ITSO + IERC" reads
    as one decision. An event with no `from_party` is the submitter sending the
    record in.
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
    suggested_offices = models.JSONField(default=list, blank=True)
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
    closed_by_decision = models.ForeignKey(
        Review, on_delete=models.RESTRICT, null=True, blank=True,
        related_name="closed_revision_requests",
    )

    class Meta:
        ordering = ["record", "created_at"]
        indexes  = [models.Index(fields=["record", "state"])]

    def __str__(self):
        return f"Record {self.record_id} | {self.party} | {self.state}"


class ReviewComment(models.Model):
    """
    One message in a record's review discussion (ADR-032 §7, IR-419).

    Private to the review: read under `may_read_review`, written by the
    record's participants, and never shown in public discussion, which is a
    separate model. Shown in the review timeline, which is derived from rows
    like this one rather than copied into an event table.
    """

    record     = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="review_comments"
    )
    #: `SET_NULL`: the discussion outlives an account that is removed.
    author     = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="review_comments",
    )
    body       = models.TextField()
    #: The record's latest Version when the comment was written. Null on a
    #: record with no version yet: no "v1" is invented (spec §4.11).
    version    = models.ForeignKey(
        "records.RecordVersion", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="review_comments",
    )
    #: The comment this one answers. Always a top-level comment on the same
    #: record: a reply to a reply joins its thread (`apps.reviews.comments`).
    reply_to   = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies",
    )
    created_at = models.DateTimeField(default=timezone.now)
    #: Stamped by an edit that changed the body; null until then.
    edited_at  = models.DateTimeField(null=True, blank=True)

    # --- a top-level comment is a thread (ADR-032 §7, 2026-11-04; IR-874) ---------
    # Every field below describes the thread, so a reply leaves them at their
    # defaults: it is never a draft, has no severity, and is never resolved.

    #: The party the thread belongs to, not the person: the writer's party when
    #: they wrote it. Blank for an owner's thread. A withdrawn writer's thread
    #: stays the party's, and its current Seat holders own it.
    party      = models.CharField(max_length=20, choices=PARTY_CHOICES, blank=True, default="")
    #: A reviewer's thread only. Existing rows were backfilled as *Suggestion*.
    severity   = models.CharField(
        max_length=20, choices=ThreadSeverity.choices, null=True, blank=True,
    )
    #: Seen only by its writer until *Finish review* sends it (`round`).
    is_draft   = models.BooleanField(default=False)
    #: The finished review that sent it; null for a thread posted directly.
    round      = models.ForeignKey(
        "ReviewRound", on_delete=models.SET_NULL, null=True, blank=True, related_name="threads",
    )

    #: An anchored thread's passage: the Version, the page, the quoted text, the
    #: text either side of it and its regions in ADR-031's page-fraction shape,
    #: so the passage can be found again in a later Version. All empty on a
    #: general thread.
    anchor_version = models.ForeignKey(
        "records.RecordVersion", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="anchored_threads",
    )
    anchor_page    = models.PositiveIntegerField(null=True, blank=True)
    anchor_quote   = models.TextField(blank=True, default="")
    anchor_prefix  = models.TextField(blank=True, default="")
    anchor_suffix  = models.TextField(blank=True, default="")
    anchor_regions = models.JSONField(default=list, blank=True)

    state       = models.CharField(
        max_length=20, choices=ThreadState.choices, default=ThreadState.OPEN,
    )
    resolved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="review_threads_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    #: The Decision that closed it while open, as Seats and requests name it.
    closed_by_decision = models.ForeignKey(
        Review, on_delete=models.RESTRICT, null=True, blank=True,
        related_name="closed_threads",
    )
    closed_reason = models.TextField(blank=True, default="")

    #: An owner's answer to a reviewer's thread: where it was addressed, or why
    #: it was declined. Answering never resolves it.
    answer      = models.CharField(max_length=20, choices=ThreadAnswer.choices, blank=True, default="")
    answer_note = models.TextField(blank=True, default="")
    answered_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="review_threads_answered",
    )
    answered_at = models.DateTimeField(null=True, blank=True)

    #: A reviewer's replacement text for an anchored passage (IR-876). Set
    #: while the thread is a draft and fixed once it is sent, so the owner
    #: accepts or declines the wording they read. Accepting is the *Addressed*
    #: answer: IRIS can't edit the PDF, so it is a promise.
    suggestion  = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["record", "created_at", "pk"]
        indexes  = [
            models.Index(fields=["record", "created_at"]),
            models.Index(fields=["record", "state", "severity"]),
        ]

    def __str__(self):
        return f"Record {self.record_id} | comment {self.pk} by {self.author_id}"


class ReviewRound(models.Model):
    """
    One finished review (ADR-032 §7, 2026-11-04; IR-874): a Seat holder sent
    their draft threads with a summary and a verdict.

    *Comment only* is a recorded round with no outcome: it writes this row and
    no `Review`, so nothing that reads `Review.status` can mistake it for one.
    Every other verdict was taken by the service that owns it, and `review` is
    the `Review` that service wrote.
    """

    record     = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="review_rounds",
    )
    actor      = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="review_rounds",
    )
    party      = models.CharField(max_length=20, choices=PARTY_CHOICES)
    version    = models.ForeignKey(
        "records.RecordVersion", on_delete=models.RESTRICT,
        null=True, blank=True, related_name="review_rounds",
    )
    verdict    = models.CharField(max_length=20, choices=ReviewVerdict.choices)
    summary    = models.TextField(blank=True, default="")
    review     = models.ForeignKey(
        Review, on_delete=models.RESTRICT, null=True, blank=True, related_name="rounds",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["record", "created_at", "pk"]
        indexes  = [models.Index(fields=["record", "created_at"])]

    def __str__(self):
        return f"Record {self.record_id} | {self.party} finished: {self.verdict}"


class ReviewThreadEvent(models.Model):
    """
    One change to a published review thread: its severity, resolving,
    reopening, an owner's answer, or a Decision closing it. Each is shown in
    the timeline with the person and the time (ADR-032 §7). A thread's
    current state is on the thread; these rows are its history.
    """

    thread     = models.ForeignKey(ReviewComment, on_delete=models.CASCADE, related_name="events")
    actor      = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="review_thread_events",
    )
    kind       = models.CharField(max_length=30, choices=ThreadEventKind.choices)
    #: The value before and after, where the change has one: a severity, an answer.
    old_value  = models.CharField(max_length=20, blank=True, default="")
    new_value  = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["thread", "created_at", "pk"]

    def __str__(self):
        return f"Thread {self.thread_id} | {self.kind}"


class ThreadPlace(models.Model):
    """
    Where an anchored thread's passage is in one later Version (ADR-032 §7,
    *Outdated threads*; IR-876). The thread's own anchor never changes: each
    later Version adds a row, found from the previous Version's place, so a
    thread follows its passage and an Outdated one still shows its original.
    """

    thread  = models.ForeignKey(ReviewComment, on_delete=models.CASCADE, related_name="places")
    version = models.ForeignKey(
        "records.RecordVersion", on_delete=models.RESTRICT, related_name="thread_places",
    )
    outcome = models.CharField(max_length=20, choices=ThreadPlaceOutcome.choices)
    #: Null when the passage was removed.
    page    = models.PositiveIntegerField(null=True, blank=True)
    #: The text here: the quote when found, the edited passage when changed.
    text    = models.TextField(blank=True, default="")
    regions = models.JSONField(default=list, blank=True)
    #: The suggested-wording hint (ADR-058 §3): the page it appears on in this
    #: Version, or null where it doesn't, or the thread carries none.
    suggestion_page = models.PositiveIntegerField(null=True, blank=True)
    placed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["thread", "version"], name="one_place_per_thread_version"),
        ]

    def __str__(self):
        return f"Thread {self.thread_id} in version {self.version_id}: {self.outcome}"


class ResponseLetter(models.Model):
    """
    The response to reviewers (ADR-032 §7; IR-876): the owner's answers to
    the open threads of the parties that asked for a revision, frozen when
    the Version answering them was submitted. Never edited afterwards.
    """

    version    = models.OneToOneField(
        "records.RecordVersion", on_delete=models.CASCADE, related_name="response_letter",
    )
    #: One entry per thread, in the letter's order (`response_letter.entries`).
    entries    = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Response letter for version {self.version_id}"


#: How many saved replies one person keeps (IR-877). Enough for a reviewer's
#: stock phrases; a ceiling because each is stored and listed in full.
MAX_SAVED_REPLIES = 50
#: The longest title a saved reply takes: a label in a menu, not a sentence.
MAX_SAVED_REPLY_TITLE = 60


class SavedReply(models.Model):
    """
    A person's own reusable text, inserted into a review comment (ADR-032 §7,
    2026-11-04 Conveniences; IR-877). Private: every queryset starts from
    `owner=request.user`, so another person's reply cannot be addressed and is
    the same 404 as a missing one. It belongs to no record, so no review
    predicate applies, and inserting one only adds text to a comment box.

    The title is unique per person ignoring case, which the database enforces.
    Kept until its owner deletes it or the account goes (the key cascades).
    Not in Django admin and writes no `AuditEvent`, like a saved feed.
    """

    owner      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_replies",
    )
    title      = models.CharField(max_length=MAX_SAVED_REPLY_TITLE)
    body       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("title"), "owner", name="unique_saved_reply_title"),
        ]

    def __str__(self):
        return f"SavedReply(owner={self.owner_id}, title={self.title!r})"


class ViewedMark(models.Model):
    """
    A person ticked a compared section as viewed (ADR-032 §7 Conveniences and
    its IR-877 build notes; ADR-058 §3 as amended, point 7). Private: read
    only for its own `user`, and decides nothing.

    **It belongs to the reading it was made on**, so it keeps that reading,
    its Version, and the section's `key` and `text_hash` there. A section's
    key can differ between two readings of one file, so a comparison shows a
    section as Viewed when this person marked a section with **its
    `text_hash`**, on this record, in any Version or reading. A later Version
    that changes the section has another hash, which is how the mark clears;
    nothing is deleted.
    """

    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="viewed_marks",
    )
    record     = models.ForeignKey("records.Record", on_delete=models.CASCADE, related_name="+")
    version    = models.ForeignKey("records.RecordVersion", on_delete=models.CASCADE, related_name="+")
    reading    = models.ForeignKey("records.ReviewText", on_delete=models.CASCADE, related_name="+")
    section_key = models.CharField(max_length=255)
    text_hash  = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "reading", "section_key"],
                                    name="one_viewed_mark_per_reading_section"),
        ]
        indexes = [models.Index(fields=["user", "record", "text_hash"], name="viewed_mark_lookup")]

    def __str__(self):
        return f"Viewed by {self.user_id}: {self.section_key[:40]} in reading {self.reading_id}"
