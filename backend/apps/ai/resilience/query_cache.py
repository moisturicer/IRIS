"""Caching query embeddings (IR-132).

One assignment sends forty students after the same thing; embedding that
question forty times is forty billable calls for one answer.

**The embedding space id is part of the key, and that is mandatory rather than
defensive.** A vector cached under a retired space and served against a current
index is a cross-space comparison: it returns rows, ranked plausibly, and
wrong. It also survives a redeploy, which is what makes it hard to find.

Only *queries* are cached. A corpus text is embedded once at ingestion and
never re-requested, and incremental re-chunking already avoids repeating that
work, so caching documents would spend memory to serve nobody.
"""

from __future__ import annotations

import hashlib
from typing import MutableMapping, Optional, Sequence

from apps.ai.providers.ports import EmbeddingProvider


def normalize_question(text: str) -> str:
    """Collapse the differences that are not differences.

    Case and whitespace: "Weekly  Pond Sampling" and "weekly pond sampling" are
    one question and should cost one call.
    """
    return " ".join(text.lower().split())


def query_cache_key(text: str, space_id: int) -> str:
    """Cache key for a query embedding under one embedding space.

    Hashed rather than concatenated so an arbitrarily long question still
    produces a bounded key -- Redis keys are cheap but not free, and a
    thousand-word paste should not become a thousand-word key.
    """
    digest = hashlib.sha256(normalize_question(text).encode("utf-8")).hexdigest()
    return f"iris:qvec:{space_id}:{digest}"


class CachingEmbeddingProvider(EmbeddingProvider):
    """Wraps an ``EmbeddingProvider``, serving repeated questions from cache.

    A decorator rather than behaviour inside an adapter, for the same reason
    the circuit breaker is: an adapter that caches internally cannot be tested
    for the call it avoided, and the fake would need the same machinery to
    remain a substitute.
    """

    def __init__(
        self,
        inner: EmbeddingProvider,
        cache: MutableMapping,
        space_id: int,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._space_id = space_id
        self._ttl = ttl_seconds

    @property
    def dimensions(self) -> int:
        return self._inner.dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._inner.embed_documents(texts)

    def embed_document_chunks(
        self, documents: Sequence[Sequence[str]]
    ) -> list[list[list[float]]]:
        # Passed straight through for the reason in the module docstring:
        # corpus text is embedded once at ingestion and never re-requested,
        # so caching it would spend memory to serve nobody.
        return self._inner.embed_document_chunks(documents)

    def embed_query(self, text: str) -> list[float]:
        key = query_cache_key(text, self._space_id)

        cached = self._cache.get(key)
        if cached is not None:
            return list(cached)

        vector = self._inner.embed_query(text)
        # Django's cache API takes a timeout; a plain mapping does not. Support
        # both so tests can pass a dict without a shim.
        try:
            self._cache.set(key, vector, self._ttl)  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            self._cache[key] = vector
        return vector
