"""The evidence decision's shadow record (IR-466, ADR-035 §10).

One row per Turn: pending -> running -> completed / failed / skipped, moved
only by `apps.ai.evidence.shadow`. Holds no model text, and cascades from the
Turn so a deleted Conversation takes it along.
"""

from django.db import models

from .conversation import Turn

PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
SKIPPED = "skipped"

_STATUS_CHOICES = [
    (PENDING, "Pending"),
    (RUNNING, "Running"),
    (COMPLETED, "Completed"),
    (FAILED, "Failed"),
    (SKIPPED, "Skipped"),
]


class ShadowEvidenceDecision(models.Model):
    turn = models.OneToOneField(
        Turn, on_delete=models.CASCADE, related_name="evidence_shadow"
    )
    status = models.CharField(max_length=12, choices=_STATUS_CHOICES, default=PENDING)
    #: Why a row ended skipped or failed, as a code. Blank when completed.
    outcome = models.CharField(max_length=40, blank=True)

    #: Each claim stamps a token; every later write must match it.
    claim_token = models.UUIDField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    claims = models.PositiveSmallIntegerField(default=0)
    reclaims = models.PositiveSmallIntegerField(default=0)
    #: Paid-for decisions the fence discarded.
    fenced_out_completions = models.PositiveSmallIntegerField(default=0)

    #: What the request ran under, for the task's parity check.
    manifest = models.JSONField()
    #: The deterministic verdict, computed in-request (`Verdict.as_dict()`).
    detector = models.JSONField()
    #: The model's route (`ModelDecision.as_dict()`), once decided.
    decision = models.JSONField(null=True, blank=True)
    #: ADR-035 §3: evidence when either half demands it.
    route = models.CharField(max_length=12, blank=True)
    parity_matched = models.BooleanField(null=True)
    parity_differences = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "claimed_at"])]

    def __str__(self) -> str:
        return f"ShadowEvidenceDecision(turn={self.turn_id}, status={self.status})"


class ShadowEvidenceTally(models.Model):
    """Counts of shadow events with no row to count them on."""

    code = models.CharField(max_length=40, unique=True)
    count = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"ShadowEvidenceTally({self.code}={self.count})"
