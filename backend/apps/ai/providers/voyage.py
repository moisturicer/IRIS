"""Voyage as the embedding and reranking provider (IR-128, ADR-015).

One vendor for both stages, no alternative in scope. `httpx`, matching the
Docling client next door rather than adding a second HTTP stack.

**What this module deliberately does not do.** No retries, no circuit breaker,
no rate limiting, no caching. Those are a decorator stack composed *around*
the ports (IR-132), not behaviour baked into an adapter -- an adapter that
retries internally cannot be tested for the failure it hides, and a fake would
have to grow the same machinery to stay a substitute.

**Nothing here decides whether content may be sent.** That is the disclosure
policy's job (IR-127), applied by the caller before a candidate reaches this
module. An adapter that consulted the gate itself would put the security
decision in the layer most likely to be swapped out.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

import httpx
from django.conf import settings

from .batching import batch_by_token_budget, estimate_tokens
from .ports import EmbeddingProvider, RerankedCandidate, Reranker

_BASE_URL = "https://api.voyageai.com/v1"

#: ADR-015: 120,000 input tokens per request with auto-chunking enabled,
#: 32,000 without. The conservative figure is used because auto-chunking is
#: not requested -- IRIS does its own chunking and does not want the vendor
#: silently re-splitting a passage whose regions are already persisted.
_EMBED_TOKEN_BUDGET = 32_000

#: Voyage's asymmetric input types. The whole reason `embed_documents` and
#: `embed_query` are separate methods (ADR-015 rule 3).
_DOCUMENT = "document"
_QUERY = "query"

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class VoyageError(RuntimeError):
    """A Voyage call failed. Raised rather than swallowed so the resilience
    decorators in IR-132 have something to catch."""


def _api_key() -> str:
    key = getattr(settings, "VOYAGE_API_KEY", "")
    if not key:
        raise VoyageError(
            "VOYAGE_API_KEY is not set. Per CLAUDE.md's environment rule the "
            "application must fail on a missing required secret rather than "
            "defaulting silently -- there is no unauthenticated Voyage mode "
            "and no local model to fall back to (ADR-008, ADR-015)."
        )
    return key


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = httpx.post(
            f"{_BASE_URL}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {_api_key()}"},
            timeout=getattr(settings, "VOYAGE_TIMEOUT_SECONDS", 60),
        )
    except httpx.HTTPError as exc:
        raise VoyageError(f"Voyage request to {path} failed: {exc}") from exc
    if response.status_code >= 400:
        raise VoyageError(
            f"Voyage returned {response.status_code} at {path}: {response.text[:300]}"
        )
    return response.json()


class VoyageEmbeddingProvider(EmbeddingProvider):
    """`voyage-context-4` by default, 1024 dimensions (ADR-015).

    ``transport`` is injectable so the request *shaping* -- which input type is
    sent, how texts are batched -- is testable without a network or an account.
    The wire call itself is one function and stays untested, which is the same
    trade the Docling client makes.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
        transport: Optional[Transport] = None,
    ) -> None:
        self._model = model or getattr(settings, "VOYAGE_EMBED_MODEL", "voyage-context-4")
        # Not a setting of its own (IR-280). What this asks Voyage to emit
        # and what the vector columns can hold are the same number, and the
        # moment they are two settings they can disagree — `VOYAGE_EMBED_
        # DIMENSIONS=512` would have produced 512-vectors for a 1024 column,
        # which is the bug class this ticket exists to close, one hop along.
        # Explicit `dimensions` stays, because a test embedding at 4 is how
        # the request shaping is asserted without an account.
        from apps.ai.models import VECTOR_COLUMN_DIMENSIONS

        self._dimensions = dimensions or VECTOR_COLUMN_DIMENSIONS
        self._post = transport or _post

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in batch_by_token_budget(texts, _EMBED_TOKEN_BUDGET, estimate_tokens):
            payload = {
                "model": self._model,
                "input": list(batch),
                "input_type": input_type,
                "output_dimension": self._dimensions,
            }
            body = self._post("/embeddings", payload)
            data = body.get("data") or []
            if len(data) != len(batch):
                raise VoyageError(
                    f"Voyage returned {len(data)} vectors for {len(batch)} inputs. "
                    "Vectors are matched to inputs positionally, so a short "
                    "response would attach the wrong vector to the wrong chunk."
                )
            vectors.extend(item["embedding"] for item in data)
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []          # no empty request to a metered API
        return self._embed(list(texts), _DOCUMENT)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], _QUERY)[0]


class VoyageReranker(Reranker):
    """`rerank-2` by default (ADR-015). Reads text, never a vector."""

    def __init__(
        self, model: Optional[str] = None, transport: Optional[Transport] = None
    ) -> None:
        self._model = model or getattr(settings, "VOYAGE_RERANK_MODEL", "rerank-2")
        self._post = transport or _post

    def rerank(
        self, query: str, candidates: Sequence[str]
    ) -> list[RerankedCandidate]:
        if not candidates:
            return []
        body = self._post(
            "/rerank",
            {"model": self._model, "query": query, "documents": list(candidates)},
        )
        results = body.get("data") or []
        if len(results) != len(candidates):
            raise VoyageError(
                f"Voyage reranked {len(results)} of {len(candidates)} candidates. "
                "The port promises every candidate back; dropping one silently "
                "removes a passage the caller may have needed."
            )
        ranked = [
            RerankedCandidate(
                index=item["index"],
                text=candidates[item["index"]],
                score=float(item["relevance_score"]),
            )
            for item in results
        ]
        return sorted(ranked, key=lambda c: (-c.score, c.index))
