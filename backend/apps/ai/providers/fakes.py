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
from typing import Iterator, Optional, Sequence

from .ports import EmbeddingProvider, LLMProvider, RerankedCandidate, Reranker, StreamDelta


#: Reserved dimension carrying the document/query marker. Reproducing
#: Voyage's asymmetry matters (ADR-015 rule 3), but a fake whose asymmetry
#: *destroys* similarity cannot stand in for one: retrieval tests would have
#: no closest passage to find. A small marker on one axis keeps
#: `embed_documents(x) != embed_query(x)` assertable while leaving cosine
#: similarity dominated by the shared tokens.
_MARKER_DIMENSION = 0
_MARKER_WEIGHT = 0.05


def _feature_vector(text: str, dimensions: int, marker: float) -> list[float]:
    """A hashed bag-of-words vector.

    Feature hashing rather than a random draw, so the fake behaves like an
    embedder in the one way the tests depend on: **text that shares words
    lands close together**. That is what lets retrieval, ranking and reranking
    be tested end to end with no vendor account -- and IR-129's tests are the
    security tests, so they must run everywhere.

    Deterministic across runs and processes: the same text always produces the
    same vector, which is the property the contract suite asserts and the one
    that makes a cached vector testable.
    """
    values = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        # Sign from a second byte, so unrelated tokens can cancel rather than
        # only ever accumulating towards one corner of the space.
        values[index] += 1.0 if digest[4] % 2 else -1.0

    values[_MARKER_DIMENSION] += marker

    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Embeds by hashing. Same text, same vector, forever.

    Documents and queries carry opposite markers, so the asymmetry ADR-015
    rule 3 exists to protect is *reproduced* rather than papered over: a test
    that accidentally embeds a query with the document method gets different
    numbers here, exactly as it would against Voyage -- while text that
    shares words still lands close, so ranking is testable.
    """

    def __init__(self, dimensions: int = 1024) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            _feature_vector(t, self._dimensions, _MARKER_WEIGHT) for t in texts
        ]

    def embed_document_chunks(
        self, documents: Sequence[Sequence[str]]
    ) -> list[list[list[float]]]:
        """Contextualized in shape, not in effect.

        A chunk's vector here depends on its own text alone, because a
        hashed bag of words has nowhere to put a document's context. That is
        the one place this fake is *not* a behavioural substitute for Voyage,
        and it is stated rather than hidden: a test asserting that context
        changes a vector cannot be written against this, and a test asserting
        the grouping reaches the wire belongs in the adapter's own suite.

        The shape it does reproduce faithfully — one list per document, in
        order — is what every caller downstream actually depends on.
        """
        return [self.embed_documents(document) for document in documents]

    def embed_query(self, text: str) -> list[float]:
        return _feature_vector(text, self._dimensions, -_MARKER_WEIGHT)


class ScriptedReranker(Reranker):
    #: A test double makes no outbound call.
    transmits_externally = False

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


class ScriptedLLM(LLMProvider):
    """A deterministic stand-in for an inference vendor.

    Echoes a citation marker back so the citation-parsing tests in
    `apps/ai/answers/` have something realistic to parse, and so the whole
    answer path is exercisable with no key and no network.
    """

    def __init__(
        self,
        reply: str = "Based on the sources, yes [1].",
        stream_deltas: Optional[Sequence[StreamDelta]] = None,
    ):
        self._reply = reply
        # ``None`` means "no script" -- `stream()` then falls through to the
        # port's own default, which wraps `generate()` as a single delta.
        # Given explicitly (IR-326), it lets a streaming test assert on
        # multiple `TextDelta` events without a vendor account.
        self._stream_deltas = stream_deltas
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._reply

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        if self._stream_deltas is None:
            yield from super().stream(system, user)
            return
        self.calls.append((system, user))
        yield from self._stream_deltas
