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
from typing import Iterator, Sequence


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
        """Embed corpus text. One vector per input, in the same order.

        Each text stands alone, with nothing else in view. That is the right
        contract for a record's title-and-abstract summary, which *is* the
        whole document; it is the wrong one for a chunk, which is why
        ``embed_document_chunks`` exists beside it.
        """

    @abstractmethod
    def embed_document_chunks(
        self, documents: Sequence[Sequence[str]]
    ) -> list[list[list[float]]]:
        """Embed chunks **grouped by the document they came from**.

        One inner sequence per document, holding that document's chunks in
        reading order; the result mirrors that shape exactly — one list of
        vectors per document, one vector per chunk, in the same order.

        The grouping is the contract, not an optimisation. ``voyage-context-4``
        is a *contextualized* chunk embedder (ADR-015): a chunk is embedded
        with its siblings visible to the model, so a passage reading "this
        approach reduced error by 12%" carries what approach it means. Flatten
        the grouping and the vector loses exactly the property the model was
        chosen for — and nothing downstream can detect the loss, because a
        context-free vector is a perfectly well-formed vector.

        Separate from ``embed_documents`` for the same reason that method is
        separate from ``embed_query``: a caller that can pass the wrong shape
        eventually does, and the mistake is invisible in the output.
        """

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


@dataclass(frozen=True)
class StreamDelta:
    """One increment of a streamed answer.

    ``text`` and ``reasoning`` are independent channels on the same type
    rather than a tagged union of two delta classes: a chunk can carry either,
    both, or (rarely) neither, and a caller relaying both channels to the
    browser (IR-323's reasoning-token foundation) reads one attribute per
    channel instead of ``isinstance``-branching on delta type.
    """

    text: str = ""
    reasoning: str = ""


class LLMProvider(ABC):
    """Text in, text out -- or text in, text out as it is produced.

    Deliberately smaller than the gateway's version of this port, which takes
    ``(prompt, context)``. Two loosely-typed strings invite a caller to shove
    retrieved passages into ``context`` and hope the adapter formats them; here
    the *caller* assembles the prompt (see `apps/ai/answers/`) and this port
    only transports it. Prompt assembly is the part with citation numbering in
    it, and it belongs in the domain where it can be tested without a vendor.
    """

    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Answer ``user`` under the instructions in ``system``.

        Separate arguments rather than one concatenated prompt: folding the
        instructions into the user turn makes them look like something the
        asker said, which is how a prompt injection sitting in an uploaded
        document ends up outranking the system prompt.
        """

    def stream(self, system: str, user: str) -> Iterator[StreamDelta]:
        """Answer incrementally, as ``StreamDelta`` chunks (IR-325).

        Concrete rather than abstract, and its default wraps ``generate``:
        every existing fake and resilience decorator that implements only
        ``generate`` keeps working unmodified, yielding its whole answer as
        one delta rather than gaining a silent behavioural gap. A provider
        that can genuinely stream -- currently only
        ``OpenAICompatibleAdapter`` -- overrides this instead.
        """
        yield StreamDelta(text=self.generate(system, user))
