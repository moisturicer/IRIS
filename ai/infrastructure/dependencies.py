from typing import Generator
from ai.infrastructure.settings import settings
from ai.domain.ports import LLMProvider, EmbeddingProvider
from ai.infrastructure.openai_adapter import OpenAILLMProvider, OpenAIEmbeddingProvider

# Singleton instances so we don't recreate clients on every request
_llm_provider = None
_embedding_provider = None

def get_llm_provider() -> LLMProvider:
    global _llm_provider
    if _llm_provider is None:
        if settings.LLM_PROVIDER == "openai":
            _llm_provider = OpenAILLMProvider()
        else:
            # An unrecognized name must raise, not silently fall through to a
            # mock adapter — that failure mode turns a typo into wrong
            # output instead of an error.
            raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER!r}")
    return _llm_provider

def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        if settings.EMBEDDING_PROVIDER == "openai":
            _embedding_provider = OpenAIEmbeddingProvider()
        else:
            raise ValueError(
                f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER!r}"
            )
    return _embedding_provider
