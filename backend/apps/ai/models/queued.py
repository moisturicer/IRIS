"""A question answered by a worker rather than the request (IR-544, ADR-040).

Three tables. `AskRun` is the owned run: who asked, in which Conversation,
the validated request, its original deadline and its one terminal outcome.
`AskRunAttempt` is one worker's go at it -- a redelivered message gets a new
attempt, and `AskRun.current_attempt` is the fencing token: only the attempt
it names may append to the journal or finish the run. `AskRunEvent` is the
ordered public journal a reader replays from a cursor.

Kept apart from `ResearchRun` on purpose: that table is the planner's private
telemetry and exists only on the research lane, while any lane can be queued.
An attempt links to the `ResearchRun` its planner wrote instead.

Everything cascades from the Conversation, so deleting one deletes its runs
and journal, and a run whose Conversation is gone cannot write a Turn.
"""

import uuid

from django.conf import settings
from django.db import models


QUEUED = "queued"
RUNNING = "running"
#: Terminal states. `succeeded` and `partial` carry a Turn; the other two do not.
SUCCEEDED = "succeeded"
PARTIAL = "partial"
FAILED = "failed"
EXPIRED = "expired"
#: The asker stopped it (IR-548). No Turn, and nothing written after.
CANCELLED = "cancelled"
TERMINAL_STATES = frozenset({SUCCEEDED, PARTIAL, FAILED, EXPIRED, CANCELLED})
#: Ended without an answer, so the asker may retry it. Not `partial`: that
#: run already wrote its fragment as a Turn, and a retry would add a second
#: Turn for the same question. The reader asks again instead.
RETRYABLE_STATES = frozenset({FAILED, EXPIRED, CANCELLED})

_RUN_STATES = [
    (s, s.title()) for s in (QUEUED, RUNNING, SUCCEEDED, PARTIAL, FAILED, EXPIRED, CANCELLED)
]


class AskRunQuerySet(models.QuerySet):
    def owned_by(self, user):
        """The whole privacy rule: a run is reachable only by its asker."""
        return self.filter(user=user)


class AskRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ask_runs"
    )
    conversation = models.ForeignKey(
        "ai.Conversation", on_delete=models.CASCADE, related_name="ask_runs"
    )
    #: The validated request body, re-read and re-authorised by the worker.
    request = models.JSONField(default=dict)
    state = models.CharField(max_length=16, choices=_RUN_STATES, default=QUEUED)
    created_at = models.DateTimeField(auto_now_add=True)
    #: Fixed at submission. A retry or redelivery never moves it.
    deadline_at = models.DateTimeField()
    #: The only attempt allowed to write. Cleared when the run ends.
    current_attempt = models.ForeignKey(
        "ai.AskRunAttempt", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_sequence = models.PositiveIntegerField(default=0)
    #: One-to-one, so a run can never own two final Turns.
    turn = models.OneToOneField(
        "ai.Turn", null=True, blank=True, on_delete=models.SET_NULL, related_name="ask_run"
    )
    #: A code: the Turn's state, or why the run ended without one.
    end_reason = models.CharField(max_length=32, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    #: The run this one retries (IR-548). One-to-one, so asking to retry the
    #: same run twice finds the first retry instead of starting another.
    retry_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="retry"
    )

    objects = AskRunQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"])]

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def __str__(self) -> str:
        return f"AskRun({self.pk}, state={self.state})"


class AskRunAttempt(models.Model):
    RUNNING = "running"
    FINISHED = "finished"
    SUPERSEDED = "superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AskRun, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveSmallIntegerField()
    state = models.CharField(max_length=16, default=RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    #: The planner's private telemetry for this attempt, when it ran one.
    research_run = models.ForeignKey(
        "ai.ResearchRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["run", "number"], name="ask_run_attempt_number"),
        ]


class AskRunEvent(models.Model):
    """One public event. Names, codes, counts and answer text; never reasoning."""

    run = models.ForeignKey(AskRun, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField()
    name = models.CharField(max_length=32)
    data = models.JSONField(default=dict)
    attempt = models.ForeignKey(
        AskRunAttempt, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["run", "sequence"], name="ask_run_event_sequence"),
        ]
