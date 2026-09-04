"""Claiming and completing a chunk-and-embed job (IR-115 G).

Two functions, because that is the whole protocol: a worker claims a key
before it spends anything, and marks it complete after. A redelivery of work
that already finished is told so and returns.

This is the one Django-touching module in ``apps.ai.ingestion`` — the
lifecycle table and the key derivation next to it are pure.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from .keys import ingestion_job_key
from .lifecycle import IngestionState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.ai.models import IngestionJob


@dataclass(frozen=True)
class JobClaim:
    """The result of claiming a key.

    ``is_duplicate`` is the whole point: when it is ``True`` the caller must
    return without embedding anything, because an identical run already
    completed. It is not an error and not a failure — it is the retry storm
    costing nothing.
    """

    job: "IngestionJob"
    is_duplicate: bool


def claim_ingestion_job(
    *, record_id: int, extraction_hash: str, strategy_id: str, space_id: int
) -> JobClaim:
    """Claim the job for these four identifying parts.

    A previously failed job is reclaimed rather than skipped: a run that
    fell over spent no budget worth protecting, and refusing to retry it
    would leave the record permanently unindexed. Only a completed
    (``Indexed``) job is reported as a duplicate.
    """
    from apps.ai.models import IngestionJob

    key = ingestion_job_key(
        record_id=record_id,
        extraction_hash=extraction_hash,
        strategy_id=strategy_id,
        space_id=space_id,
    )

    with transaction.atomic():
        job, created = IngestionJob.objects.select_for_update().get_or_create(
            idempotency_key=key,
            defaults={
                "record_id": record_id,
                "extraction_hash": extraction_hash,
                "strategy_id": strategy_id,
                "space_id": space_id,
            },
        )
        if created:
            return JobClaim(job=job, is_duplicate=False)

        if job.state == IngestionState.INDEXED:
            return JobClaim(job=job, is_duplicate=True)

        if job.state == IngestionState.FAILED:
            job.transition_to(IngestionState.EXTRACTED)
            job.save(update_fields=["state", "error", "updated_at"])

        return JobClaim(job=job, is_duplicate=False)


def complete_ingestion_job(job: "IngestionJob", *, content_hash: str) -> "IngestionJob":
    """Mark ``job`` indexed and record the chunk set hash it indexed.

    The hash is what a later run compares against to decide staleness, so
    storing it is not bookkeeping — it is the thing that makes the next run
    free when nothing changed.
    """
    with transaction.atomic():
        if job.state == IngestionState.EXTRACTED:
            job.transition_to(IngestionState.CHUNKED)
        job.transition_to(IngestionState.INDEXED)
        job.content_hash = content_hash
        job.save(
            update_fields=[
                "state",
                "error",
                "content_hash",
                "completed_at",
                "updated_at",
            ]
        )
    return job
