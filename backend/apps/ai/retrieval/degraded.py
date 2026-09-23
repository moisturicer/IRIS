"""Degrading to full-text search when the vendor is unreachable (IR-132).

ADR-008 already chose the fallback: PostgreSQL full-text search, the same path
the system used before vectors existed. This wires it to the circuit breaker so
a Voyage outage degrades search instead of taking the feature down.

**The degraded path uses the same visibility predicate as the healthy one.**
There used to be a second record-level FTS module filtered by
`publicly_visible()` -- a *different*, narrower predicate -- and reusing it
here would have meant the answer a reader gets depends on whether the vendor
happened to be up. ADR-014 rejected that, so this fallback searches chunks
through `visible_to(user)` like everything else. IR-285 then deleted the other
module outright, so the choice is no longer available to make wrongly.

**The indication reaches the caller as data, in the result itself.** It used
to ride on a `list` subclass so that a caller could iterate unchanged; that
ergonomic is what let `RerankingRetriever` drop it (IR-279). It is now a field
on `RetrievalResult`, which a decorator has to work to lose.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

from apps.ai.models.chunk import DocumentChunk
from apps.ai.regions import normalized_regions
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.resilience.rate_limit import RateLimited
from apps.records.models import Record

from .ports import FULL_TEXT, RetrievalResult, RetrievedChunk, Retriever

logger = logging.getLogger(__name__)


def is_vendor_unavailable(exc: BaseException) -> bool:
    """The two failures this module can name without importing an adapter
    (IR-132): IRIS's own resilience signals, raised only when a vendor call
    was refused outright (an open circuit) or already over its own budget (a
    spent rate limit).

    Exported so a composition root can extend it with a vendor-specific
    ``.kind`` check -- a raw ``VoyageError`` is not always one of these two,
    see ``composition._vendor_failures`` (IR-320) -- without duplicating this
    half of the decision.
    """
    return isinstance(exc, (CircuitOpen, RateLimited))


class FullTextRetriever(Retriever):
    """Chunk-level FTS, visibility-filtered exactly like the vector path.

    Builds the search vector at query time rather than storing one:
    `Record.search_vector` is maintained for records, chunks have no equivalent
    column, and adding one is a migration and an index this path does not
    justify -- it runs only while the vendor is down.

    ``record``, like `TwoStageRetriever`'s, narrows the search to one Record
    (IR-298) -- constructed by the composition root, not threaded through
    `retrieve`, so a degraded Paper Chat answer keeps its scope instead of
    quietly widening because the vendor happened to be down.
    """

    def __init__(self, record: Optional[Record] = None) -> None:
        self._record = record

    def retrieve(self, question: str, user, limit: int = 20):
        if not question.strip():
            return RetrievalResult(degraded=True, mode=FULL_TEXT)

        visible = Record.objects.visible_to(user)
        if self._record is not None:
            visible = visible.filter(pk=self._record.pk)
        visible = visible.values("pk")
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
            .select_related("record", "chunk_set")
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
                    regions=normalized_regions(
                        row.bboxes, row.chunk_set.page_sizes
                    ),
                )
                for row in rows
            ),
            degraded=True,
            mode=FULL_TEXT,
        )


class DegradableRetriever(Retriever):
    """Tries the vector path; falls back to full text when the vendor is out.

    Only falls back for failures that mean *the vendor is unavailable* --
    an open circuit, an exhausted rate limit, a network or timeout failure. A
    bug in our own query is not a vendor outage, and silently returning
    keyword results for it would hide the bug behind slightly worse answers,
    which is how a defect survives a release. Nor is every vendor error an
    outage (IR-320): an auth failure or a rejected oversized prompt will fail
    identically against full text, so degrading past them would hide a real
    problem the same way.

    ``degrade_on`` is a predicate rather than a tuple of exception types,
    because that distinction cannot be made by type alone -- a single vendor
    exception (``VoyageError``) can be either kind of failure, and only its
    ``.kind`` attribute says which.
    """

    def __init__(
        self,
        primary: Retriever,
        fallback: Optional[Retriever] = None,
        degrade_on: Callable[[BaseException], bool] = is_vendor_unavailable,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or FullTextRetriever()
        self._should_degrade = degrade_on

    def retrieve(self, question: str, user, limit: int = 20):
        try:
            results = self._primary.retrieve(question, user, limit=limit)
        except Exception as exc:
            if not self._should_degrade(exc):
                raise
            logger.warning(
                "retrieval degraded to full-text search: %s", exc, exc_info=False
            )
            return self._fallback.retrieve(question, user, limit=limit)

        # Returned as it came: the primary is a `Retriever`, so its result
        # already says how it was produced. Rewrapping it here is what would
        # overwrite that.
        return results
