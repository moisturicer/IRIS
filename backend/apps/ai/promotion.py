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


def promote(space, *, actor: str = "", provider_factory=None, verify_index: bool = True) -> None:
    """Make ``space`` the active one, retiring whichever space held that.

    Delegates to ``apps.ai.space_activation`` (IR-739), which verifies the
    whole Record-and-Passage pair -- coverage, widths, query/document
    semantics, current revisions and index health -- and then flips both
    levels in one transaction, retiring the previous space rather than
    deleting it (IR-280: vectors point at a space with ``on_delete=CASCADE``,
    so a deleted space would take its vectors, and a rollback's target, with
    it). Raises ``PromotionRefused`` naming every reason, changing nothing.

    A pending space that is the recorded rollback target is activated as a
    rollback; anything else is a promotion.
    """
    from apps.ai.space_activation import activate_space, rollback_target

    target = rollback_target()
    kind = "rollback" if target is not None and target.pk == space.pk else "promote"
    activate_space(
        space.pk, kind=kind, actor=actor,
        provider_factory=provider_factory, verify_index=verify_index,
    )
    space.refresh_from_db()
