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

from dataclasses import replace
from typing import Callable, Optional, Sequence

from apps.ai.policy import decision_for_record
from apps.ai.providers.noop import NoOpReranker
from apps.ai.providers.ports import Reranker
from apps.records.models import Record

from .diagnostics import (
    ChunkBuckets,
    RetrievalConfiguration,
    StageDiagnostics,
    chunk_ids,
)
from .ports import RetrievalResult, RetrievedChunk, Retriever

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
    return decision_for_record(record).allowed


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

    @property
    def _gate_runs(self) -> bool:
        """Whether the gate evaluates anything at all on this configuration.

        A property rather than a repeated condition because IR-459 needs the
        same answer twice: once to decide whether to gate, and once to record
        whether a withheld count was observable.
        """
        return self._policy_enabled and self._reranker.transmits_externally

    def _permitted(self, candidates: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        """Drop anything the disclosure policy refuses.

        Applied **before** the reranker is called, never to its results:
        filtering afterwards means the text has already left the deployment,
        which is the exact thing ADR-015's gate exists to prevent.

        Only consulted when the reranker actually transmits. A reranker that
        makes no outbound call exposes nothing, so gating it would withhold
        passages from the asking user to protect them from themselves.
        """
        if not self._gate_runs:
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

    # -- what the recall stage saw ------------------------------------------

    def _configuration(self, inner: RetrievalResult, limit: int):
        """The configuration the recall counts mean something under (IR-459).

        `withheld` of 8 out of 8 reads one way under a recall limit of 100 and
        a transmitting reranker, and another under a no-op one -- so the
        numbers travel with the settings that produced them.
        """
        return RetrievalConfiguration(
            mode=inner.mode,
            degraded=inner.degraded,
            embedding_space_id=inner.embedding_space_id,
            recall_limit=self._recall_limit,
            requested_limit=limit,
            reranker=type(self._reranker).__name__,
            reranker_transmits=self._reranker.transmits_externally,
            disclosure_gate=self._gate_runs,
        )

    def _observed(
        self,
        inner: RetrievalResult,
        limit: int,
        recalled: Sequence[RetrievedChunk],
        survivors: Sequence[RetrievedChunk],
        kept: Sequence[RetrievedChunk],
    ) -> StageDiagnostics:
        """Partition the candidates this stage actually saw (IR-459).

        `below_floor` stays absent rather than zero: no relevance floor exists
        at this stage, so nothing here could have measured one (IR-396).

        `gate_evaluated` is empty rather than absent when the gate did not run
        -- it ran on nothing, which is observed, and is not the same fact as a
        stage that never existed.
        """
        recalled_ids = chunk_ids(recalled)
        survivor_ids = chunk_ids(survivors)
        kept_ids = chunk_ids(kept)
        return StageDiagnostics(
            buckets=ChunkBuckets(
                withheld=recalled_ids - survivor_ids,
                kept=kept_ids,
                not_selected=survivor_ids - kept_ids,
                gate_evaluated=recalled_ids if self._gate_runs else frozenset(),
            ),
            configuration=self._configuration(inner, limit),
        )

    # -- the port -----------------------------------------------------------

    def retrieve(self, question: str, user, limit: int = 20) -> RetrievalResult:
        # The inner result is carried through rather than unpacked and
        # rebuilt: this decorator reorders passages, and everything else it
        # was told -- that the vendor was out, which path ran, which space --
        # is not its to restate (IR-279).
        inner = self._inner.retrieve(question, user, limit=self._recall_limit)
        candidates = self._permitted(inner.passages)
        if not candidates:
            return inner.with_passages(
                (),
                diagnostics=self._observed(inner, limit, inner.passages, (), ()),
            )

        key = self._cache_key(question, candidates)
        if self._cache is not None and key in self._cache:
            order = self._cache[key]
        else:
            ranked = self._reranker.rerank(question, [c.content for c in candidates])
            order = [(item.index, item.score) for item in ranked]
            if self._cache is not None:
                self._cache[key] = order

        # `replace`, not a field-by-field rebuild: this decorator changes the
        # score and nothing else, and listing every other field here is how a
        # field added to `RetrievedChunk` silently stops surviving reranking
        # (IR-334 -- `regions` would have been the first).
        kept = [
            replace(candidates[index], score=score)
            for index, score in order
        ][:limit]
        return inner.with_passages(
            kept,
            diagnostics=self._observed(inner, limit, inner.passages, candidates, kept),
        )
