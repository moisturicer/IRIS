from abc import ABC, abstractmethod
from typing import List


class UnsupportedCapability(Exception):
    """The provider cannot serve this request; nothing is substituted."""


class TransientProviderError(Exception):
    """A sent attempt failed in a way another attempt may not (IR-725)."""


class LLMProvider(ABC):
    """
    Abstract Base Class for LLM providers (e.g. OpenAI).
    """

    @abstractmethod
    async def generate_response(self, prompt: str, context: str = "") -> str:
        """
        Generate a response based on the prompt and context.
        """
        pass

    def accepts(self, pin) -> bool:
        """Whether this provider serves an AGENT `Pin` exactly (IR-727)."""
        return False

    async def converse(self, request):
        """One AGENT model turn for an `ai.agent.protocol.AgentRequest`.

        Concrete so existing adapters stay valid; they refuse.
        """
        raise UnsupportedCapability("converse")

class EmbeddingProvider(ABC):
    """
    Abstract Base Class for embedding providers.

    Document and query embedding are separate methods, not one method with a
    flag. Voyage-class models are asymmetric — a document and the query used
    to retrieve it are embedded with different input types, and mixing them
    degrades retrieval measurably (ADR-015). A boolean parameter makes the
    wrong call possible; two methods make it impossible.

    Document embedding is batched (one round trip for many chunks); query
    embedding is single-text, because a query is embedded once per question,
    on the request path.
    """

    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of document texts, in order.

        Returns one vector per input text, in the same order — callers rely
        on positional correspondence to attach each vector back to its chunk.
        """
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query string for retrieval.

        Kept distinct from ``embed_documents`` even for a provider whose
        underlying model treats both the same way (see
        ``OpenAIEmbeddingProvider``): the two-method shape is what prevents a
        caller from silently mixing input types on a provider where it does
        matter.
        """
        raise NotImplementedError
