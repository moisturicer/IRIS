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

    #: Whether reranking sends candidate text outside the deployment.
    #:
    #: The disclosure gate (IR-127) exists to stop record content reaching a
    #: commercial vendor. A reranker that makes no outbound call transmits
    #: nothing, so withholding candidates from it protects nobody and costs
    #: recall. Declared on the port rather than inferred from the class name,
    #: because the caller has to branch on it and guessing is how a real
    #: transmission ends up ungated.
    transmits_externally: bool = True

    @abstractmethod
    def rerank(
        self, query: str, candidates: Sequence[str]
    ) -> list[RerankedCandidate]:
        """Return every candidate, in descending score order.

        Every candidate, not the top few: trimming is the caller's decision
        and it needs the scores to make it. Implementations must not drop,
        duplicate or rewrite a candidate.
        """


class LLMProvider(ABC):
    """Text in, text out.

    Deliberately smaller than the gateway's version of this port, which takes
    ``(prompt, context)``. Two loosely-typed strings invite a caller to shove
    retrieved passages into ``context`` and hope the adapter formats them; here
    the *caller* assembles the prompt (see `apps/ai/answers/`) and this port
    only transports it. Prompt assembly is the part with citation numbering in
    it, and it belongs in the domain where it can be tested without a vendor.

    One method, and no streaming: ADR-017's streaming work is gateway-side and
    gated on an ASGI deployment IRIS does not yet run.
    """

    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Answer ``user`` under the instructions in ``system``.

        Separate arguments rather than one concatenated prompt: folding the
        instructions into the user turn makes them look like something the
        asker said, which is how a prompt injection sitting in an uploaded
        document ends up outranking the system prompt.
        """
