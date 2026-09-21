"""Two-stage retrieval: candidate records, then chunks within them (IR-129).

Stage 1 ranks *records* on the summary-level `RecordEmbedding`; stage 2 ranks
*chunks* belonging only to the records stage 1 kept. That is what makes chunk
search affordable -- a few dozen records is roughly a thousand chunks rather
than the whole corpus.

**Visibility is applied in stage 1, before anything is scored.** Not as a
filter over results, and not as a permission check at the view: the candidate
set is narrowed by `Record.objects.visible_to(user)` first, so a chunk the
asker cannot read is never ranked, never sent to a reranker, and never paid
for. `visible_to` is the one predicate `RecordViewSet` already applies on
every action (IR-153) -- ADR-014 rejected a second implementation on the
grounds that two definitions of who-can-see-what will drift, and the drift is
a confidentiality breach rather than a bug.

Retrieval runs in **Django, never the gateway** (ADR-014 precondition 4, which
that ADR calls not negotiable). The gateway is handed text and returns
numbers; it holds no database connection, so there is no second path around
the permission layer.
"""

from __future__ import annotations

from typing import Optional

from pgvector.django import CosineDistance

from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace, EmbeddingSpaceState
from apps.ai.providers.ports import EmbeddingProvider
from apps.records.models import Record

from .ports import VECTOR, RetrievalResult, RetrievedChunk, Retriever

#: Stage 1 keeps this many records. ADR-013's sizing: a few dozen records is
#: roughly a thousand chunks, which is a cheap stage-2 search.
DEFAULT_RECORD_CANDIDATES = 40

#: Stage 2 returns this many chunks by default. Deliberately wider than an
#: answer needs: reranking only improves on what recall found, so IR-130
#: raises this and trims afterwards rather than narrowing here.
DEFAULT_CHUNK_LIMIT = 20


class TwoStageRetriever(Retriever):
    def __init__(
        self,
        embedder: EmbeddingProvider,
        record_candidates: int = DEFAULT_RECORD_CANDIDATES,
        space: Optional[EmbeddingSpace] = None,
    ) -> None:
        self._embedder = embedder
        self._record_candidates = record_candidates
        self._space = space

    def _active_space(self) -> Optional[EmbeddingSpace]:
        if self._space is not None:
            return self._space
        return EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.ACTIVE).first()

    def retrieve(self, question: str, user, limit: int = DEFAULT_CHUNK_LIMIT):
        space = self._active_space()
        if space is None:
            # No active space means nothing was ever indexed under one. Return
            # nothing rather than guessing a space: comparing vectors across
            # spaces returns rows, ranked plausibly, and wrong.
            return RetrievalResult(mode=VECTOR)

        query_vector = self._embedder.embed_query(question)

        # -- Stage 1: candidate records, visibility-filtered before scoring --
        visible_records = Record.objects.visible_to(user).values("pk")
        candidate_ids = list(
            RecordEmbedding.objects.filter(record__in=visible_records)
            .order_by(CosineDistance("embedding", query_vector))
            .values_list("record_id", flat=True)[: self._record_candidates]
        )
        if not candidate_ids:
            return RetrievalResult(
                mode=VECTOR, embedding_space_id=space.pk, query_vector=query_vector
            )

        # -- Stage 2: chunks within those records only --
        distance = CosineDistance("embedding", query_vector)
        rows = (
            ChunkEmbedding.objects.filter(
                space=space,
                # `DocumentChunk` carries a denormalized `record` FK, so this
                # narrows without joining through the chunk set.
                chunk__record_id__in=candidate_ids,
                chunk__chunk_set__is_active=True,
                chunk__deleted_at__isnull=True,
            )
            .select_related("chunk", "chunk__record")
            .annotate(distance=distance)
            .order_by("distance")[:limit]
        )

        return RetrievalResult(
            passages=tuple(
                RetrievedChunk(
                    chunk_id=row.chunk_id,
                    record_id=row.chunk.record_id,
                    record_title=row.chunk.record.title,
                    content=row.chunk.content,
                    context_path=tuple(row.chunk.context_path or ()),
                    source_page=row.chunk.source_page,
                    # Cosine distance runs 0 (identical) to 2; similarity is
                    # the complement, so a larger score is a better match
                    # whichever metric a future space uses.
                    score=1.0 - float(row.distance),
                )
                for row in rows
            ),
            mode=VECTOR,
            embedding_space_id=space.pk,
            query_vector=query_vector,
        )
