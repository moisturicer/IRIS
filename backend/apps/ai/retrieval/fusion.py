"""Hybrid retrieval: the keyword and vector lists, merged by rank (IR-395).

ADR-033 §1. A dense embedding blurs an exact identifier, a surname or an
uncommon acronym, and `FullTextRetriever` -- which matches one exactly, and is
already visibility-correct -- was reachable only while the vendor was down.

Two searches over the whole visible catalogue, merged by rank position with no
constant: ADR-033 rejected score normalisation because its constant is fitted
to the queries it was chosen on. Fusion sits inside reranking, so the merged
list meets the disclosure gate and the reranker exactly as the vector list
does. Visibility stays one `visible_to(user)` filter, inside each search --
ADR-033 §Security Impact adds a candidate source, never a second rule.

Off by default (`AI_KEYWORD_RETRIEVAL_ENABLED`, `AI_RETRIEVAL_FUSION_ENABLED`);
ADR-033 §5 gives the defaults to IR-402.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Hashable, Iterable, Sequence, TypeVar

from .ports import RetrievalResult, RetrievedChunk, Retriever

T = TypeVar("T")


def fuse_by_rank(
    lists: Iterable[Sequence[T]],
    key: Callable[[T], Hashable],
) -> list[T]:
    """Interleave ranked lists by position, keeping each item's best rank.

    Rank 1 of every list, then rank 2, and so on; an item found twice is
    emitted at its first position, so being found twice can promote it and
    never demote it. Within one position, the order of ``lists`` breaks the tie.

    No weight, threshold or ``k`` -- which is the argument for this shape over
    adding normalised scores, since a fitted constant is a parameter and a
    parameter has to be tuned on questions.

    Pure and passage-agnostic on purpose: IR-399's sub-question merge and
    Listing questions reuse it, which is why ADR-033 §1 asks for the merge as
    its own unit.
    """
    ranked = [list(items) for items in lists]
    depth = max((len(items) for items in ranked), default=0)

    seen: set[Hashable] = set()
    merged: list[T] = []
    for position in range(depth):
        for items in ranked:
            if position >= len(items):
                continue
            item = items[position]
            identity = key(item)
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(item)
    return merged


def _at_position(passage: RetrievedChunk, position: int) -> RetrievedChunk:
    """The passage carrying its merged position as its score.

    A `ts_rank` (~0.06) and a cosine similarity (~0.8) in one list would make
    the field mean two things at once, and `presentation.record_sources` reads
    it for a record card's headline score. The reciprocal of the merged
    position is monotone with the merged order, so a consumer that sorts by
    score agrees with it. A position, not a relevance -- ADR-033 §3 forbids
    showing a retrieval score to a reader, and with reranking on the reranker
    replaces it.
    """
    return replace(passage, score=1.0 / (position + 1))


class KeywordFusionRetriever(Retriever):
    """Runs a keyword search alongside ``inner`` and merges the two by rank.

    Returns ``inner_result.with_passages(...)``, never a fresh result:
    constructing one resets ``degraded`` and loses ``mode`` and
    ``embedding_space_id``, the defect IR-279 fixed.

    An already-degraded result is passed straight through -- it *is* full-text
    search, so fusing it with full-text search buys a query and no candidates.
    `DegradableRetriever` sits outside, so in the composed stack this cannot
    arise; a retriever that would run the redundant query if it did is one
    waiting to be recomposed wrongly.
    """

    def __init__(self, inner: Retriever, keyword: Retriever) -> None:
        self._inner = inner
        self._keyword = keyword

    def retrieve(self, question: str, user, limit: int = 20) -> RetrievalResult:
        inner = self._inner.retrieve(question, user, limit=limit)
        if inner.degraded:
            return inner

        # Only the passages are taken. `FullTextRetriever` reports
        # `degraded=True` for its usual caller, the outage path; on the healthy
        # path that would tell a reader the vendor was out.
        keyword = self._keyword.retrieve(question, user, limit=limit)

        # Vector first, so it breaks ties at equal rank: it is the list this
        # deployment already answers from, and fusion adds candidates rather
        # than reordering the ones already working.
        #
        # This trims back to `limit`, so a keyword hit *displaces* a vector
        # candidate rather than joining it -- substitution, where ADR-033
        # §Decision Rationale says "widens what reaches the reranker". Left as
        # measured and raised as IR-438 rather than changed here: widening is a
        # second change, and it would invalidate the run that earned this one.
        merged = fuse_by_rank(
            (inner.passages, keyword.passages),
            key=lambda passage: passage.chunk_id,
        )[:limit]

        return inner.with_passages(
            [_at_position(passage, position) for position, passage in enumerate(merged)]
        )
