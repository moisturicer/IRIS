"""Making an Embedding Space live, and refusing to when it is not ready
(IR-282).

An Embedding Space that goes active half-indexed answers questions
confidently from the half of the corpus it happens to hold. That is worse
than answering nothing: a reader cannot see the missing half, and neither can
the ranking — a chunk with no vector does not score low, it does not exist.

So promotion is a **separate command from the backfill**, and it refuses
unless every active chunk in the corpus has a vector in the space being
promoted. Nothing promotes automatically; ``EmbeddingSpace``'s own docstring
already says that flipping which space is active is an operational decision
rather than a migration, and this is where that is enforced.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction


class PromotionRefused(Exception):
    """The space is not fully indexed, so it may not go live."""


@dataclass(frozen=True)
class Shortfall:
    """One record that would be partly invisible under this space."""

    record_id: int
    title: str
    missing: int
    total: int


def records_missing_vectors(space_id: int, *, limit: int = 0) -> list[Shortfall]:
    """Every record holding an active chunk with no vector in ``space_id``.

    Named per record rather than counted in aggregate because "4,910 chunks
    short" tells an operator nothing they can act on, while "record 36 is
    short 12 of 47" points at a job that failed.
    """
    from apps.records.models import Record

    from django.db.models import Count, Q

    queryset = (
        Record.objects.annotate(
            active_chunks=Count(
                "document_chunks",
                filter=Q(
                    document_chunks__chunk_set__is_active=True,
                    document_chunks__deleted_at__isnull=True,
                ),
                distinct=True,
            ),
            embedded_chunks=Count(
                "document_chunks",
                filter=Q(
                    document_chunks__chunk_set__is_active=True,
                    document_chunks__deleted_at__isnull=True,
                    document_chunks__embeddings__space_id=space_id,
                ),
                distinct=True,
            ),
        )
        .filter(active_chunks__gt=0)
        .order_by("pk")
    )

    shortfalls = [
        Shortfall(
            record_id=record.pk,
            title=record.title,
            missing=record.active_chunks - record.embedded_chunks,
            total=record.active_chunks,
        )
        for record in queryset
        if record.embedded_chunks < record.active_chunks
    ]
    return shortfalls[:limit] if limit else shortfalls


def promote(space) -> None:
    """Make ``space`` the active one, retiring whichever space held that.

    One transaction, and the retire lands before the promote: the partial
    unique index ``one_active_embedding_space`` is checked per statement, so
    the other order fails on a database that is behaving correctly.

    Retired rather than deleted, for the reason IR-280 recorded — vectors
    point at a space with ``on_delete=CASCADE``, so deleting one takes its
    vectors with it, and a rollback would then have nothing to roll back to.
    """
    from apps.ai.models import (
        VECTOR_COLUMN_DIMENSIONS,
        EmbeddingSpace,
        EmbeddingSpaceState,
    )

    # Completeness is not the only thing that makes a space unfit to be
    # live. A retired space is one the project has already decided against,
    # and `indexing._checked_space` refuses to *write* to one — the two
    # would otherwise disagree about the same row. A space whose width does
    # not match the vector columns cannot hold a readable vector at all.
    if space.state == EmbeddingSpaceState.RETIRED:
        raise PromotionRefused(
            f"Space {space.pk} is retired. Promoting one the project has "
            f"already retired makes live what it decided against; create a "
            f"new space instead."
        )
    if space.dimensions != VECTOR_COLUMN_DIMENSIONS:
        raise PromotionRefused(
            f"Space {space.pk} is {space.dimensions} dimensions but the "
            f"vector columns hold {VECTOR_COLUMN_DIMENSIONS}. Queries against "
            f"it would compare vectors of different widths."
        )

    shortfalls = records_missing_vectors(space.id)
    if shortfalls:
        raise PromotionRefused(
            f"{len(shortfalls)} record(s) have active chunks with no vector in "
            f"space {space.id} ({space.model_id}). A space promoted half-indexed "
            f"answers confidently from the half it holds."
        )

    with transaction.atomic():
        EmbeddingSpace.objects.filter(
            state=EmbeddingSpaceState.ACTIVE
        ).exclude(pk=space.pk).update(state=EmbeddingSpaceState.RETIRED)
        EmbeddingSpace.objects.filter(pk=space.pk).update(
            state=EmbeddingSpaceState.ACTIVE
        )
    space.refresh_from_db()
