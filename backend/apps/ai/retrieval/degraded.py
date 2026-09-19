"""Degrading to full-text search when the vendor is unreachable (IR-132).

ADR-008 already chose the fallback: PostgreSQL full-text search, the same path
the system used before vectors existed. This wires it to the circuit breaker so
a Voyage outage degrades search instead of taking the feature down.

**The degraded path uses the same visibility predicate as the healthy one.**
`apps/ai/services/retrieval.py` also does FTS, but at record level and through
`publicly_visible()` -- a *different*, narrower predicate. Reusing it here would
mean the answer a reader gets depends on whether the vendor happened to be up,
and would put a second visibility rule on the retrieval path. ADR-014 rejected
exactly that for exactly that reason, so the fallback searches chunks through
`visible_to(user)` like everything else.

**The indication reaches the caller as data, in the result itself.** It used
to ride on a `list` subclass so that a caller could iterate unchanged; that
ergonomic is what let `RerankingRetriever` drop it (IR-279). It is now a field
on `RetrievalResult`, which a decorator has to work to lose.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

from apps.ai.models.chunk import DocumentChunk
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.resilience.rate_limit import RateLimited
from apps.records.models import Record

from .ports import FULL_TEXT, RetrievalResult, RetrievedChunk, Retriever

logger = logging.getLogger(__name__)


class FullTextRetriever(Retriever):
    """Chunk-level FTS, visibility-filtered exactly like the vector path.

    Builds the search vector at query time rather than storing one:
    `Record.search_vector` is maintained for records, chunks have no equivalent
    column, and adding one is a migration and an index this path does not
    justify -- it runs only while the vendor is down.
    """

    def retrieve(self, question: str, user, limit: int = 20):
        if not question.strip():
            return RetrievalResult(degraded=True, mode=FULL_TEXT)

        visible = Record.objects.visible_to(user).values("pk")
        query = SearchQuery(question, config="english")
        vector = SearchVector("content", config="english")

        rows = (
            DocumentChunk.objects.filter(
                record__in=visible,
                chunk_set__is_active=True,
                deleted_at__isnull=True,
            )
            .annotate(rank=SearchRank(vector, query))
            .filter(rank__gt=0)
            .select_related("record")
            .order_by("-rank")[:limit]
        )

        return RetrievalResult(
            passages=tuple(
                RetrievedChunk(
                    chunk_id=row.pk,
                    record_id=row.record_id,
                    record_title=row.record.title,
                    content=row.content,
                    context_path=tuple(row.context_path or ()),
                    source_page=row.source_page,
                    score=float(row.rank),
                )
                for row in rows
            ),
            degraded=True,
            mode=FULL_TEXT,
        )


class DegradableRetriever(Retriever):
    """Tries the vector path; falls back to full text when the vendor is out.

    Only falls back for failures that mean *the vendor is unavailable* --
    an open circuit, an exhausted rate limit, a vendor error. A bug in our own
    query is not a vendor outage, and silently returning keyword results for it
    would hide the bug behind slightly worse answers, which is how a defect
    survives a release.
    """

    def __init__(
        self,
        primary: Retriever,
        fallback: Optional[Retriever] = None,
        degrade_on: tuple[type[BaseException], ...] = (CircuitOpen, RateLimited),
    ) -> None:
        self._primary = primary
        self._fallback = fallback or FullTextRetriever()
        self._degrade_on = degrade_on

    def retrieve(self, question: str, user, limit: int = 20):
        try:
            results = self._primary.retrieve(question, user, limit=limit)
        except self._degrade_on as exc:
            logger.warning(
                "retrieval degraded to full-text search: %s", exc, exc_info=False
            )
            return self._fallback.retrieve(question, user, limit=limit)

        # Returned as it came: the primary is a `Retriever`, so its result
        # already says how it was produced. Rewrapping it here is what would
        # overwrite that.
        return results
