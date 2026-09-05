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
    """Construct the one embedding adapter directly.

    No name-keyed branch here: IRIS has exactly one embedding provider
    (ADR-015), so a switch would just be a second place, independent of
    Django's ``EmbeddingSpace``, where the two ends of the pipeline could
    silently disagree about what produced a vector. Swap the concrete class
    here when the adapter changes; a test that needs a different one
    constructs ``DeterministicFakeEmbeddingProvider`` directly rather than
    routing through a setting.
    """
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = OpenAIEmbeddingProvider()
    return _embedding_provider
