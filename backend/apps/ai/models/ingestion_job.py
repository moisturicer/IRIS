"""The chunk-and-embed job (IR-115 G): an idempotency key and a state.

The row exists for one reason — so that a duplicate delivery from Celery
finds work already done and returns without spending the token budget again.
Everything else on it is in service of that: ``idempotency_key`` is what a
redelivery collides with, ``state`` is what says whether the work finished,
and ``content_hash`` is what says whether it is still valid.

The state machine itself lives in ``apps.ai.ingestion.lifecycle``, which is
pure. This model applies it; it does not restate it. ``transition_to`` is the
only way to change ``state``, so a disallowed move raises rather than being
written.
"""

from django.db import models
from django.utils import timezone

from apps.ai.ingestion.lifecycle import (
    IngestionState,
    StateLike,
    assert_transition,
    staleness_after,
)


class IngestionJob(models.Model):
    """One chunk-and-embed run, keyed on what determines its output.

    The four key parts are the record, the extraction, the strategy and the
    embedding space: change any one of them and the vectors differ; change
    none and re-running is pure waste.
    """

    record = models.ForeignKey(
        "records.Record", on_delete=models.CASCADE, related_name="ingestion_jobs"
    )
    extraction_hash = models.CharField(max_length=64)
    strategy_id = models.CharField(max_length=100)
    space = models.ForeignKey(
        "ai.EmbeddingSpace", on_delete=models.CASCADE, related_name="ingestion_jobs"
    )
    idempotency_key = models.CharField(max_length=64, unique=True)
    # Extracted, not Uploaded: there is no key without an extraction hash, so
    # a claimed job is past that state by construction.
    state = models.CharField(
        max_length=20,
        choices=[(s.value, s.name.title()) for s in IngestionState],
        default=IngestionState.EXTRACTED.value,
        db_index=True,
    )
    # The chunk set hash this job indexed. Empty until it completes; after
    # that it is the only thing staleness is derived from.
    content_hash = models.CharField(max_length=64, blank=True, default="")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # The key is a digest of exactly these four columns, so the
            # constraint below is redundant with the unique key by
            # construction. It is here so the invariant survives a change to
            # how the digest is computed, and so the schema states the
            # business rule rather than only its hash.
            models.UniqueConstraint(
                fields=["record", "extraction_hash", "strategy_id", "space"],
                name="unique_ingestion_job_identity",
            ),
        ]

    def __str__(self) -> str:
        return f"IngestionJob(record={self.record_id}, state={self.state})"

    def transition_to(self, target: StateLike, *, error: str = "") -> IngestionState:
        """Move to ``target``, or raise ``IllegalTransition``.

        Does not save — the caller decides the transaction boundary, and a
        transition is usually one part of a larger unit of work.
        """
        new_state = assert_transition(self.state, target)
        self.state = new_state.value
        self.error = error
        if new_state is IngestionState.INDEXED:
            self.completed_at = timezone.now()
        return new_state

    def refresh_staleness(self, *, current_hash: str) -> IngestionState:
        """Apply :func:`~apps.ai.ingestion.lifecycle.staleness_after` to this
        row. That function is the only path to ``Stale``, and this is the
        only caller that writes the result — so there is no argument here by
        which a user could ask for a document to be marked stale.
        """
        new_state = staleness_after(
            self.state, stored_hash=self.content_hash, current_hash=current_hash
        )
        self.state = new_state.value
        return new_state
