from abc import ABC, abstractmethod
from typing import List

class LLMProvider(ABC):
    """
    Abstract Base Class for LLM providers (e.g. OpenAI, Ollama).
    """
    @abstractmethod
    async def generate_response(self, prompt: str, context: str = "") -> str:
        """
        Generate a response based on the prompt and context.
        """
        pass

class EmbeddingProvider(ABC):
    """
    Abstract Base Class for Embedding providers.
    """
    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate a vector embedding for the given text.
        """
        pass
