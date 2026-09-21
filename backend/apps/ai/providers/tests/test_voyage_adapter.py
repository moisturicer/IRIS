"""What the Voyage adapters put on the wire (IR-128).

No account and no network: ``transport`` is injected, so the part with the
judgement in it -- which input type is sent, how texts are batched, what
happens when the vendor returns the wrong number of things -- is tested, and
the one function that actually makes the HTTP call is not. Same trade as the
Docling client.

The contract suite in ``test_provider_contracts.py`` additionally runs these
adapters against the real API when ``VOYAGE_API_KEY`` is present.
"""

import pytest

from apps.ai.providers.ports import RerankedCandidate
from apps.ai.providers.voyage import (
    VoyageEmbeddingProvider,
    VoyageError,
    VoyageReranker,
)

# `voyage.py` reads `django.conf.settings` for the key and model names, so
# unlike the ports, the fakes and the batching next door, this module needs
# Django installed. No database, though.
pytestmark = pytest.mark.django_required


class _RecordingTransport:
    """A stand-in wire that remembers what it was asked to send."""

    def __init__(self, dimensions=4, short_by=0):
        self.calls = []
        self.dimensions = dimensions
        self.short_by = short_by

    def __call__(self, path, payload):
        self.calls.append((path, payload))
        if path == "/embeddings":
            count = len(payload["input"]) - self.short_by
            return {"data": [{"embedding": [0.1] * self.dimensions} for _ in range(count)]}
        docs = payload["documents"]
        return {
            "data": [
                {"index": i, "relevance_score": 1.0 - (i / 10)}
                for i in range(len(docs) - self.short_by)
            ]
        }


class EmbeddingRequestTests:
    def test_documents_and_queries_send_different_input_types(self):
        """ADR-015 rule 3 is only real if the asymmetry reaches the wire."""
        transport = _RecordingTransport()
        provider = VoyageEmbeddingProvider(dimensions=4, transport=transport)

        provider.embed_documents(["alpha"])
        provider.embed_query("alpha")

        assert [payload["input_type"] for _, payload in transport.calls] == [
            "document",
            "query",
        ]

    def test_the_configured_dimension_is_requested_explicitly(self):
        transport = _RecordingTransport()
        VoyageEmbeddingProvider(dimensions=4, transport=transport).embed_documents(["a"])
        assert transport.calls[0][1]["output_dimension"] == 4

    def test_embedding_nothing_makes_no_request_to_a_metered_api(self):
        transport = _RecordingTransport()
        assert VoyageEmbeddingProvider(transport=transport).embed_documents([]) == []
        assert transport.calls == []

    def test_a_large_input_is_split_across_requests_by_token_budget(self):
        transport = _RecordingTransport()
        provider = VoyageEmbeddingProvider(dimensions=4, transport=transport)
        # Each text is ~20k tokens, so three cannot share one 32k-token
        # request. Counted with the real tokenizer since IR-287, so the size
        # here is what Voyage would actually charge rather than an estimate.
        texts = [" ".join(["clearance-aware"] * 10_000) for _ in range(3)]

        vectors = provider.embed_documents(texts)

        assert len(transport.calls) > 1, "one oversized request was sent"
        assert len(vectors) == 3, "every input still gets exactly one vector"

    def test_a_short_response_raises_rather_than_misaligning_vectors(self):
        """Vectors are matched to inputs positionally. A short response would
        attach the wrong vector to the wrong chunk, which no later stage can
        detect."""
        provider = VoyageEmbeddingProvider(
            dimensions=4, transport=_RecordingTransport(short_by=1)
        )
        with pytest.raises(VoyageError, match="positionally"):
            provider.embed_documents(["alpha", "beta"])


class RerankRequestTests:
    def test_every_candidate_comes_back_with_its_original_index(self):
        reranker = VoyageReranker(transport=_RecordingTransport())
        result = reranker.rerank("q", ["alpha", "beta", "gamma"])

        assert [r.index for r in result] == [0, 1, 2]
        assert [r.text for r in result] == ["alpha", "beta", "gamma"]
        assert all(isinstance(r, RerankedCandidate) for r in result)

    def test_results_are_sorted_by_descending_score(self):
        reranker = VoyageReranker(transport=_RecordingTransport())
        scores = [r.score for r in reranker.rerank("q", ["a", "b", "c"])]
        assert scores == sorted(scores, reverse=True)

    def test_reranking_nothing_makes_no_request(self):
        transport = _RecordingTransport()
        assert VoyageReranker(transport=transport).rerank("q", []) == []
        assert transport.calls == []

    def test_a_dropped_candidate_raises_rather_than_silently_shrinking(self):
        reranker = VoyageReranker(transport=_RecordingTransport(short_by=1))
        with pytest.raises(VoyageError, match="every candidate"):
            reranker.rerank("q", ["alpha", "beta"])


class MissingKeyTests:
    def test_the_real_transport_refuses_without_a_key(self, settings):
        """CLAUDE.md: the app fails on a missing required secret rather than
        defaulting silently. There is no unauthenticated Voyage mode and no
        local model to fall back to."""
        settings.VOYAGE_API_KEY = ""
        with pytest.raises(VoyageError, match="VOYAGE_API_KEY"):
            VoyageEmbeddingProvider().embed_documents(["alpha"])
