"""Embed text through the configured embedding provider (IR-156).

The second module `api/chat.py` imported and that never existed.

**Query embedding, deliberately.** `EmbeddingProvider` exposes
`embed_documents` and `embed_query` as separate methods rather than one method
with a flag, because Voyage-class models are asymmetric and mixing input types
degrades retrieval measurably (ADR-015). This service exposes one text at a
time on the request path, so it calls `embed_query`.

Batch document embedding is **not** exposed here on purpose: it belongs to the
indexing path, which runs in Django's worker against chunks Django owns
(IR-108). Putting it behind an HTTP endpoint would invite a caller to embed a
corpus one request at a time and silently pay per-request latency for work the
port already batches.
"""

from __future__ import annotations

from typing import List

from ai.domain.ports import EmbeddingProvider


class EmbeddingService:
    def __init__(self, embedder: EmbeddingProvider) -> None:
        self._embedder = embedder

    async def create_embedding(self, text: str) -> List[float]:
        """Embed one query string.

        Returns the raw vector. The caller reports its dimension rather than
        this service asserting one: the dimension is a property of the active
        `EmbeddingSpace` (ADR-015), and hardcoding an expectation here is how
        the model and the migration came to disagree about 1536 in the first
        place.
        """
        if not text or not text.strip():
            raise ValueError("text must not be empty")
        return await self._embedder.embed_query(text)
