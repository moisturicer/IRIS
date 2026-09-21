"""The reranker that does nothing, and the default (IR-128).

ADR-015 makes reranking optional and measurable rather than assumed: IR-133
compares retrieval with and without it on the same questions. That comparison
only works if switching it off is a *configuration* change, which in turn only
works if this is a genuine substitute for a real reranker -- same input and
output shape, order preserved -- rather than a special case callers branch on.
"""

from __future__ import annotations

from typing import Sequence

from .ports import RerankedCandidate, Reranker

#: Every candidate scores the same. A no-op that invented a ranking would be
#: making a claim it has no basis for, and one that scored 0.0 would look like
#: a real reranker rejecting everything.
_NEUTRAL_SCORE = 1.0


class NoOpReranker(Reranker):
    #: Nothing leaves the deployment, so the disclosure gate has nothing
    #: to protect here.
    transmits_externally = False

    def rerank(
        self, query: str, candidates: Sequence[str]
    ) -> list[RerankedCandidate]:
        return [
            RerankedCandidate(index=i, text=text, score=_NEUTRAL_SCORE)
            for i, text in enumerate(candidates)
        ]
