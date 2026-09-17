"""Reranking, wired around retrieval rather than into it (IR-130).

A decorator over any ``Retriever``: it widens recall, applies the disclosure
gate, reranks what survives, and trims to what the caller asked for. The
retriever it wraps is unchanged, which is what keeps IR-129's visibility
guarantee a property of one place.

Reranking composes with any embedding space because a reranker reads text and
never touches a vector -- so turning one on requires no re-indexing, and
turning it off is a configuration change rather than a code path. That is what
makes IR-133's with-and-without comparison possible at all.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from apps.ai.policy import inputs_for_record, may_disclose
from apps.ai.providers.noop import NoOpReranker
from apps.ai.providers.ports import Reranker
from apps.records.models import Record

from .ports import RetrievedChunk, Retriever

#: How many candidates to recall before reranking. Retrieving a handful and
#: reranking that handful achieves nothing: recall is cheap in Postgres and
#: precision is what the reranker sells, so it needs something to improve on.
DEFAULT_RECALL_LIMIT = 100


def disclosure_permits(record: Record) -> bool:
    """Whether this record's content may be sent to a commercial vendor.

    The default predicate, and a deliberately injectable one. ``Record``
    carries no embargo field yet (IR-250), so ``inputs_for_record`` reports
    ``EmbargoUnknown`` and this refuses **everything** -- correct for a gate,
    and currently total. Injecting the predicate is how a test exercises the
    allowing path without patching a module or faking a dataclass, and how a
    caller with a different notion of disclosure supplies one.
    """
    return may_disclose(inputs_for_record(record)).allowed


class RerankingRetriever(Retriever):
    def __init__(
        self,
        inner: Retriever,
        reranker: Optional[Reranker] = None,
        recall_limit: int = DEFAULT_RECALL_LIMIT,
        policy_enabled: bool = True,
        cache: Optional[dict] = None,
        permits: Callable[[Record], bool] = disclosure_permits,
    ) -> None:
        self._inner = inner
        self._reranker = reranker or NoOpReranker()
        self._recall_limit = recall_limit
        self._policy_enabled = policy_enabled
        # A plain mapping is enough to express the *key*, which is the part
        # with a decision in it. The Redis-backed, replica-safe cache is
        # IR-132's; this keeps the shape honest until then.
        self._cache = cache
        self._permits = permits

    # -- the disclosure gate ------------------------------------------------

    def _permitted(self, candidates: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        """Drop anything the disclosure policy refuses.

        Applied **before** the reranker is called, never to its results:
        filtering afterwards means the text has already left the deployment,
        which is the exact thing ADR-015's gate exists to prevent.

        Only consulted when the reranker actually transmits. A reranker that
        makes no outbound call exposes nothing, so gating it would withhold
        passages from the asking user to protect them from themselves.
        """
        if not self._policy_enabled or not self._reranker.transmits_externally:
            return list(candidates)

        record_ids = {c.record_id for c in candidates}
        records = Record.objects.filter(pk__in=record_ids).in_bulk()
        allowed = {rid for rid, record in records.items() if self._permits(record)}
        return [c for c in candidates if c.record_id in allowed]

    # -- caching ------------------------------------------------------------

    def _cache_key(self, question: str, candidates: Sequence[RetrievedChunk]):
        """Question plus the candidate id set.

        The ids matter as much as the question: the same question over a
        changed corpus is a different reranking, and serving the previous one
        would rank passages that are no longer there.
        """
        return (question, tuple(sorted(c.chunk_id for c in candidates)))

    # -- the port -----------------------------------------------------------

    def retrieve(self, question: str, user, limit: int = 20) -> list[RetrievedChunk]:
        candidates = self._inner.retrieve(question, user, limit=self._recall_limit)
        candidates = self._permitted(candidates)
        if not candidates:
            return []

        key = self._cache_key(question, candidates)
        if self._cache is not None and key in self._cache:
            order = self._cache[key]
        else:
            ranked = self._reranker.rerank(question, [c.content for c in candidates])
            order = [(item.index, item.score) for item in ranked]
            if self._cache is not None:
                self._cache[key] = order

        return [
            RetrievedChunk(
                chunk_id=candidates[index].chunk_id,
                record_id=candidates[index].record_id,
                record_title=candidates[index].record_title,
                content=candidates[index].content,
                context_path=candidates[index].context_path,
                source_page=candidates[index].source_page,
                score=score,
            )
            for index, score in order
        ][:limit]
