"""The vendor seams for the query lane (IR-128).

Two ports, both **synchronous**. The gateway's own ports (`ai/domain/ports.py`)
are async because they sit behind FastAPI; these are Django's, and Django is
the side that owns retrieval ([ADR-014] precondition 4). Until the gateway's
five preconditions hold, ADR-014 explicitly permits `apps/ai` to call the
provider ports in-process, which is what these are for.

Kept as narrow as they can be: a caller hands over text and gets back numbers
or an ordering. Nothing about batching, retries, rate limits or keys belongs
in the contract, because a fake has none of those and a fake that has to
pretend is not a substitute.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


class EmbeddingProvider(ABC):
    """Text in, vectors out.

    ``embed_documents`` and ``embed_query`` are **separate methods, not one
    method with a flag** (ADR-015 rule 3). Voyage-class models are asymmetric:
    a document and a query of identical text embed differently, and a boolean
    parameter makes calling the wrong one possible. Two methods make it
    impossible.
    """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Width of the vectors this provider returns.

        Exposed so a caller can assert it against the active ``EmbeddingSpace``
        instead of discovering a mismatch as a database error, or worse as
        plausible-looking wrong rankings.
        """

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed corpus text. One vector per input, in the same order."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a question. Asymmetric to ``embed_documents`` by design."""


@dataclass(frozen=True)
class RerankedCandidate:
    """One candidate after reranking.

    ``index`` is the position the candidate held in the input. Callers hold
    chunks rather than strings, and without the original index a reranked
    result cannot be mapped back to the chunk it came from -- which is the
    whole point of reranking in a retrieval pipeline.
    """

    index: int
    text: str
    score: float


class Reranker(ABC):
    """Reorder candidates by how well they answer the question.

    Reads text and never touches a vector, which is why a reranker composes
    with any embedding space and why turning one on requires no re-indexing.
    """

    @abstractmethod
    def rerank(
        self, query: str, candidates: Sequence[str]
    ) -> list[RerankedCandidate]:
        """Return every candidate, in descending score order.

        Every candidate, not the top few: trimming is the caller's decision
        and it needs the scores to make it. Implementations must not drop,
        duplicate or rewrite a candidate.
        """
