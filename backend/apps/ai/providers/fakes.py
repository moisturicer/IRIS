"""Deterministic stand-ins for the vendor ports (IR-128).

Real implementations, not mock objects. A mock asserts that a call *sequence*
happened; these produce genuine output from genuine input, so a test fails
when the contract changes rather than when an incidental call order does.

Nothing here touches a network, so the whole query lane is testable without a
vendor account -- which matters because the retrieval tests in IR-129 are the
security tests, and a security test that only runs where a paid API key is
configured is a security test that does not run.
"""

from __future__ import annotations

import hashlib
import math
from typing import Sequence

from .ports import EmbeddingProvider, RerankedCandidate, Reranker


def _unit_vector_from(text: str, dimensions: int, salt: str) -> list[float]:
    """A stable unit vector derived from the text itself.

    Hash-derived rather than random so the same text always embeds the same
    way, across runs and processes -- the property the contract suite asserts
    and the one that makes a cached vector testable. Normalised because cosine
    distance is what the HNSW indexes are built for, and unnormalised vectors
    would make similarity scores depend on text length.
    """
    raw = hashlib.sha256(f"{salt}:{text}".encode("utf-8")).digest()
    # Stretch the digest to the requested width; 32 bytes is rarely enough.
    while len(raw) < dimensions:
        raw += hashlib.sha256(raw).digest()
    values = [(byte / 255.0) - 0.5 for byte in raw[:dimensions]]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Embeds by hashing. Same text, same vector, forever.

    Documents and queries use different salts, so the asymmetry ADR-015 rule 3
    exists to protect is *reproduced* rather than papered over: a test that
    accidentally embeds a query with the document method gets different
    numbers here, exactly as it would against Voyage.
    """

    def __init__(self, dimensions: int = 1024) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [_unit_vector_from(t, self._dimensions, "document") for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return _unit_vector_from(text, self._dimensions, "query")


class ScriptedReranker(Reranker):
    """Scores by word overlap with the query.

    A fixed, explainable rule rather than a random one: a test can predict
    which candidate should win and assert it, which is what makes the
    with-and-without-reranking comparison in IR-133 meaningful before a vendor
    is wired in.
    """

    def rerank(
        self, query: str, candidates: Sequence[str]
    ) -> list[RerankedCandidate]:
        wanted = set(query.lower().split())
        scored = [
            RerankedCandidate(
                index=i,
                text=text,
                score=len(wanted & set(text.lower().split())) / (len(wanted) or 1),
            )
            for i, text in enumerate(candidates)
        ]
        # Stable on ties: equal scores keep input order, so the output is
        # deterministic rather than dependent on sort implementation.
        return sorted(scored, key=lambda c: (-c.score, c.index))
