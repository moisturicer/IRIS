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

from .batching import batch_documents_by_token_budget, estimate_tokens
from .errors import ClassifiedError, ErrorKind, classify_status_code
from .ports import EmbeddingProvider, RerankedCandidate, Reranker

_BASE_URL = "https://api.voyageai.com/v1"

#: ADR-015: 120,000 input tokens per request with auto-chunking enabled,
#: 32,000 without. The conservative figure is used because auto-chunking is
#: not requested -- IRIS does its own chunking and does not want the vendor
#: silently re-splitting a passage whose regions are already persisted.
#:
#: Held ~3% below the cap rather than at it (IR-287). The headroom used to be
#: hidden in the estimator, which rounded a word count up by 1.4; the
#: estimator now counts exactly, with ``add_special_tokens=False``, so it
#: reports the text's own cost and not whatever wrapping Voyage adds around
#: it. Sitting exactly on the cap with an exact count leaves nothing for that
#: difference, and the failure mode is a 400 on a full batch.
_VENDOR_TOKEN_CAP = 32_000
_EMBED_TOKEN_BUDGET = 31_000

#: `voyage-context-4` is served from the *contextualized* endpoint, not the
#: flat `/embeddings` one (IR-281). Every embedding call this adapter makes
#: goes here, including the single-text ones: the flat endpoint serves the
#: standard models, and sending a contextualized model's traffic to it
#: discards the sibling-chunk context that is the entire reason ADR-015 chose
#: this model. One path also means one place where the request shape, the
#: batching rule and the short-response guard live.
_CONTEXTUALIZED_PATH = "/contextualizedembeddings"

#: Voyage's asymmetric input types. The whole reason `embed_documents` and
#: `embed_query` are separate methods (ADR-015 rule 3).
_DOCUMENT = "document"
_QUERY = "query"

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class VoyageError(RuntimeError):
    """A Voyage call failed. Raised rather than swallowed so the resilience
    decorators in IR-132 have something to catch.

    ``kind`` adds *why*, without widening that boundary (IR-320): every
    existing catch site still just catches ``VoyageError``, and a caller that
    wants to branch on the reason reads ``.kind`` rather than a Voyage-specific
    exception this type would otherwise have to grow one of.
    """

    def __init__(self, message: str, kind: ErrorKind = ErrorKind.UNKNOWN) -> None:
        super().__init__(message)
        self.kind = kind


def _api_key() -> str:
    key = getattr(settings, "VOYAGE_API_KEY", "")
    if not key:
        raise VoyageError(
            "VOYAGE_API_KEY is not set. Per CLAUDE.md's environment rule the "
            "application must fail on a missing required secret rather than "
            "defaulting silently -- there is no unauthenticated Voyage mode "
            "and no local model to fall back to (ADR-008, ADR-015).",
            kind=ErrorKind.AUTH,
        )
    return key


def _classify_transport_error(exc: httpx.HTTPError) -> ClassifiedError:
    """Classify a failure that never got a response back (IR-320).

    ``httpx.TimeoutException`` is the one subtype worth distinguishing from
    every other transport failure -- a dropped connection, a DNS failure, a
    reset -- which all mean the same thing to a caller: the wire, not the
    vendor's application logic, is where this failed.
    """
    if isinstance(exc, httpx.TimeoutException):
        return ClassifiedError(ErrorKind.TIMEOUT, exc)
    return ClassifiedError(ErrorKind.NETWORK, exc)


def _classify_response(response: httpx.Response) -> ErrorKind:
    """Classify a failure the vendor did answer, just with an error status.

    Read by status code alone, not a parsed error body: Voyage's error-body
    shape is not documented here and guessing at one risks silently mis-typing
    a real failure. The status code is the one thing this can trust.
    """
    return classify_status_code(response.status_code, None, response.text)


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = httpx.post(
            f"{_BASE_URL}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {_api_key()}"},
            timeout=getattr(settings, "VOYAGE_TIMEOUT_SECONDS", 60),
        )
    except VoyageError:
        raise
    except httpx.HTTPError as exc:
        classified = _classify_transport_error(exc)
        raise VoyageError(
            f"Voyage request to {path} failed: {exc}", kind=classified.kind
        ) from exc
    if response.status_code >= 400:
        raise VoyageError(
            f"Voyage returned {response.status_code} at {path}: {response.text[:300]}",
            kind=_classify_response(response),
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

    def _embed_grouped(
        self, documents: Sequence[Sequence[str]], input_type: str
    ) -> list[list[list[float]]]:
        """One request shape for every embedding call this adapter makes.

        ``inputs`` is a list of documents, each a list of that document's
        chunks — the contextualized endpoint's own shape. A caller with
        standalone texts passes each as a one-chunk document, which is what
        makes ``embed_documents`` and ``embed_query`` thin wrappers rather
        than a second wire format to keep in step with this one.
        """
        grouped = [list(document) for document in documents]
        vectors: list[list[list[float]]] = []
        for batch in batch_documents_by_token_budget(
            grouped, _EMBED_TOKEN_BUDGET, estimate_tokens
        ):
            payload = {
                "model": self._model,
                "inputs": batch,
                "input_type": input_type,
                "output_dimension": self._dimensions,
            }
            body = self._post(_CONTEXTUALIZED_PATH, payload)
            data = body.get("data") or []
            if len(data) != len(batch):
                raise VoyageError(
                    f"Voyage returned {len(data)} document groups for "
                    f"{len(batch)} inputs. Groups are matched to documents "
                    "positionally, so a short response would attach one "
                    "document's vectors to another."
                )
            for group, document in zip(data, batch):
                items = group.get("data") or []
                if len(items) != len(document):
                    raise VoyageError(
                        f"Voyage returned {len(items)} vectors for a document "
                        f"of {len(document)} chunks. Vectors are matched to "
                        "chunks positionally, so a short response would attach "
                        "the wrong vector to the wrong chunk."
                    )
                vectors.append([item["embedding"] for item in items])
        return vectors

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []          # no empty request to a metered API
        # Each text is its own single-chunk document: it has no siblings, and
        # inventing some by bundling unrelated records into one group would
        # contextualize each vector against text it has nothing to do with.
        grouped = self._embed_grouped([[text] for text in texts], _DOCUMENT)
        return [vectors[0] for vectors in grouped]

    def embed_document_chunks(
        self, documents: Sequence[Sequence[str]]
    ) -> list[list[list[float]]]:
        non_empty = [list(document) for document in documents]
        if not non_empty or not any(non_empty):
            return [[] for _ in non_empty]
        if not all(non_empty):
            raise VoyageError(
                "A document with no chunks was passed to embed_document_chunks. "
                "The endpoint would return no group for it, and the result "
                "would silently shift every later document's vectors by one."
            )
        return self._embed_grouped(non_empty, _DOCUMENT)

    def embed_query(self, text: str) -> list[float]:
        return self._embed_grouped([[text]], _QUERY)[0][0]


class VoyageReranker(Reranker):
    """`rerank-3` by default (ADR-015, pinned 2026-09-20). Reads text, never a vector."""

    def __init__(
        self, model: Optional[str] = None, transport: Optional[Transport] = None
    ) -> None:
        self._model = model or getattr(settings, "VOYAGE_RERANK_MODEL", "rerank-3")
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
