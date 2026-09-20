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

from pgvector.django import CosineDistance

from apps.ai.models.embedding import RecordEmbedding
from apps.records.models import Record

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
    seed: Optional[RecordEmbedding] = RecordEmbedding.objects.filter(
        record=record
    ).first()
    if seed is None:
        # Nothing to compare *from*. Not an error — see the module docstring.
        return []

    # Only vectors written by the **same model** are comparable. `RecordEmbedding`
    # records the model on the row rather than pointing at an `EmbeddingSpace`,
    # so this is the scoping the chunk path gets from `space=space`. Without it,
    # a half-finished re-index compares a `voyage-context-4` vector against
    # whatever preceded it and returns rankings that look ordinary and mean
    # nothing — the failure mode the Embedding Space exists to prevent, arriving
    # by a different door.
    visible = Record.objects.visible_to(user).values("pk")
    rows = (
        RecordEmbedding.objects.filter(
            record__in=visible, model_name=seed.model_name
        )
        .exclude(record_id=record.pk)
        .select_related("record", "record__classification")
        .prefetch_related("record__authors")
        .annotate(distance=CosineDistance("embedding", seed.embedding))
        .order_by("distance")[:limit]
    )

    # Cosine distance runs 0 (identical) to 2, so the complement is cosine
    # similarity: 1 for the same direction, 0 for unrelated, negative for
    # opposed. Negative is a real value and not clamped — the same convention
    # `TwoStageRetriever` uses, because both scores end up in the same
    # interface and two conventions there would be worse than one signed number.
    return [
        SimilarRecord(record=row.record, score=1.0 - float(row.distance))
        for row in rows
    ]
