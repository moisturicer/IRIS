"""Which records are about the same thing (IR-285, ADR-029 §5).

One vector per record, compared directly — not chunk-level. A record vector is
built from title and abstract, so it answers "are these two broadly about the
same thing?" and **will miss** the more interesting case: two papers on
different topics sharing a method, described in the middle of each document.
ADR-029 §5 records that limit, and records that the chunk-level version is a
follow-up to build when there is a reason, not a seam to abstract for now.

**Visibility is `visible_to(user)`, applied before anything is scored** — the
same predicate as `TwoStageRetriever`, `FullTextRetriever` and
`RecordViewSet`. This module exists because `GET /records/<id>/similar/` was
the last caller of a record-level full-text search filtered by
`publicly_visible()`, a second and narrower rule. Two definitions of
who-can-see-what drift, and the drift is a confidentiality breach rather than
a bug (ADR-014).

**What this does not do**, stated because the endpoint looks the same from
outside: it does not fall back to keyword matching when nothing is indexed.
A record with no vector has no neighbours here, and today that is every
record — the disclosure gate refuses them all while `Record` carries no
embargo field (IR-250). An empty panel is the honest rendering of "nothing is
indexed"; a keyword fallback would hide that behind plausible results and put
the second visibility rule back on the path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from pgvector.django import CosineDistance

from apps.ai.models.embedding import RecordEmbedding
from apps.ai.retrieval.scan_depth import scan_depth
from apps.records.models import Record
from core.enums import PUBLICLY_VISIBLE_STATUSES, RecordTypeName

#: What the related-works panel shows. Three, because it sits beside a paper
#: rather than being the page; a caller wanting more passes more.
DEFAULT_LIMIT = 3


@dataclass(frozen=True)
class SimilarRecord:
    """One neighbour and how close it is.

    A named pair rather than a tuple, following ``RetrievedChunk`` next door:
    ``for record, score in matches`` reads fine until someone writes
    ``for score, record``, and a frozen value with two fields cannot be
    unpacked the wrong way round without saying so.
    """

    record: Record
    #: Cosine similarity: 1 for the same direction, 0 unrelated, negative for
    #: opposed. Signed on purpose — see the note where it is computed.
    score: float


def similar_records(
    record: Record, user, limit: int = DEFAULT_LIMIT
) -> list[SimilarRecord]:
    """Records closest to ``record``, nearest first, that ``user`` may read.

    Returns ``SimilarRecord`` rather than bare records: the score is what lets
    a caller say *how* related something is, and recomputing it outside would
    mean a second query against the same vectors.

    The seed record is excluded. A record seeded with its own vector matches
    itself perfectly, so leaving it in would fill the panel with the paper the
    reader already has open.
    """
    seed = _seed(record)
    if seed is None:
        # Nothing to compare *from*. Not an error — see the module docstring.
        return []
    return _nearest(seed, Record.objects.visible_to(user), limit=limit)


def related_published_research(record: Record, user) -> Optional[list[SimilarRecord]]:
    """The Novelty check: published work close to a Proposal (IR-312).

    ADR-029 §2 and its 2026-09-26 amendment, item 9: "Related published
    research" on the owner's own Proposal, recomputed on every view.

    Returns ``None`` when no comparison was made -- the record is not a
    Proposal (§1: only a Proposal is the subject), or it has no vector yet --
    so a caller can tell "not checked" from "checked, nothing close". Every
    Proposal is unchecked until IR-250 lets the corpus be indexed, and showing
    that as "nothing close" would be a claim the check never made.

    **Candidates are published records that are not Proposals.** Published is
    the public catalogue, which is why no consent is consulted: nothing here
    is new to anyone. Another Proposal is collaboration matching (IR-310),
    with its own consent and rules, not novelty. ``visible_to`` still applies,
    so the one visibility predicate governs this path too.

    Nothing under ``AI_NOVELTY_MIN_SIMILARITY`` is returned: no close match
    is an empty list rather than a weak one.
    """
    if record.record_type is None or record.record_type.name != RecordTypeName.PROPOSAL:
        return None
    seed = _seed(record)
    if seed is None:
        return None
    completed = (
        Record.objects.visible_to(user)
        .filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
        .exclude(record_type__name=RecordTypeName.PROPOSAL)
    )
    return _nearest(
        seed, completed, limit=DEFAULT_LIMIT,
        min_similarity=settings.AI_NOVELTY_MIN_SIMILARITY,
    )


def verify_novelty_configuration() -> None:
    """Refuse to start with a threshold no cosine similarity can mean (IR-312).

    Above 1 -- "70", read as a percentage -- nothing ever matches; at or below
    0 every unrelated paper does. Either looks like a working feature, so it
    is refused at startup rather than degraded silently. Called from
    ``AiConfig.ready``.
    """
    value = settings.AI_NOVELTY_MIN_SIMILARITY
    if not 0 < value <= 1:
        raise ImproperlyConfigured(
            f"AI_NOVELTY_MIN_SIMILARITY must be a cosine similarity in (0, 1], "
            f"got {value!r}. Write 0.7, not 70."
        )


def _seed(record: Record) -> Optional[RecordEmbedding]:
    return RecordEmbedding.objects.filter(record=record).first()


def _nearest(
    seed: RecordEmbedding,
    candidates,
    *,
    limit: int,
    min_similarity: Optional[float] = None,
) -> list[SimilarRecord]:
    """The ``limit`` nearest of ``candidates`` to ``seed``, excluding itself.

    ``candidates`` is the caller's Record queryset, which already carries the
    visibility predicate. The one query both related-works paths run, so a fix
    to it reaches both.
    """
    # Only vectors written by the **same model** are comparable. `RecordEmbedding`
    # records the model on the row rather than pointing at an `EmbeddingSpace`,
    # so this is the scoping the chunk path gets from `space=space`. Without it,
    # a half-finished re-index compares a `voyage-context-4` vector against
    # whatever preceded it and returns rankings that look ordinary and mean
    # nothing — the failure mode the Embedding Space exists to prevent, arriving
    # by a different door.
    rows = (
        RecordEmbedding.objects.filter(
            record__in=candidates.values("pk"), model_name=seed.model_name
        )
        .exclude(record_id=seed.record_id)
        .select_related("record", "record__classification")
        .prefetch_related("record__authors")
        .annotate(distance=CosineDistance("embedding", seed.embedding))
    )
    if min_similarity is not None:
        rows = rows.filter(distance__lte=1.0 - min_similarity)

    # HNSW scans `hnsw.ef_search` rows (40 by default) *before* the filters
    # above apply, so unwidened, a neighbourhood crowded with unreadable,
    # unpublished or other-model vectors returns too few rows and says nothing
    # (IR-440). Evaluated inside the block: a lazy queryset run later uses 40.
    with scan_depth():
        found = list(rows.order_by("distance")[:limit])

    # Cosine distance runs 0 (identical) to 2, so the complement is cosine
    # similarity: 1 for the same direction, 0 for unrelated, negative for
    # opposed. Negative is a real value and not clamped — the same convention
    # `TwoStageRetriever` uses, because both scores end up in the same
    # interface and two conventions there would be worse than one signed number.
    return [
        SimilarRecord(record=row.record, score=1.0 - float(row.distance))
        for row in found
    ]
