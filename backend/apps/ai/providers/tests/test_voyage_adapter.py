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
    """A stand-in wire that remembers what it was asked to send.

    It answers the *contextualized* embedding shape, because that is the only
    embedding endpoint the adapter calls (IR-281): a list of document groups,
    each holding one vector per chunk of that document.

    ``short_by`` drops that many vectors from every group, and ``drop_groups``
    drops whole groups off the end — two different vendor lies, and the
    adapter has to catch both, since one misaligns chunks within a document
    and the other misaligns documents against each other.
    """

    def __init__(self, dimensions=4, short_by=0, drop_groups=0):
        self.calls = []
        self.dimensions = dimensions
        self.short_by = short_by
        self.drop_groups = drop_groups

    def __call__(self, path, payload):
        self.calls.append((path, payload))
        if path == "/contextualizedembeddings":
            groups = [
                {
                    "index": i,
                    "data": [
                        {"embedding": [0.1] * self.dimensions, "index": j}
                        for j in range(max(len(document) - self.short_by, 0))
                    ],
                }
                for i, document in enumerate(payload["inputs"])
            ]
            if self.drop_groups:
                groups = groups[: len(groups) - self.drop_groups]
            return {"data": groups}
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
        # Each text is ~14k estimated tokens, so three cannot share one
        # 32k-token request.
        texts = [" ".join(["word"] * 10_000) for _ in range(3)]

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


class ContextualizedEmbeddingTests:
    """IR-281. `voyage-context-4` is a contextualized chunk embedder, and the
    only thing that makes it one is that a document's chunks travel together
    to the contextualized endpoint. None of that is observable in the vectors
    it returns, so it has to be asserted on the wire."""

    def test_every_embedding_call_goes_to_the_contextualized_endpoint(self):
        transport = _RecordingTransport()
        provider = VoyageEmbeddingProvider(dimensions=4, transport=transport)

        provider.embed_documents(["alpha"])
        provider.embed_query("alpha")
        provider.embed_document_chunks([["alpha", "beta"]])

        assert {path for path, _ in transport.calls} == {"/contextualizedembeddings"}

    def test_a_documents_chunks_are_sent_as_one_group_in_reading_order(self):
        transport = _RecordingTransport()
        provider = VoyageEmbeddingProvider(dimensions=4, transport=transport)

        provider.embed_document_chunks([["first", "second", "third"]])

        _, payload = transport.calls[0]
        assert payload["inputs"] == [["first", "second", "third"]]

    def test_two_documents_stay_two_groups_rather_than_one_flat_list(self):
        """Flattening would embed one thesis's chunks in another's context,
        which is worse than no context: the vector would be wrong rather
        than merely thin, and nothing downstream could tell."""
        transport = _RecordingTransport()
        provider = VoyageEmbeddingProvider(dimensions=4, transport=transport)

        provider.embed_document_chunks([["a1", "a2"], ["b1"]])

        _, payload = transport.calls[0]
        assert payload["inputs"] == [["a1", "a2"], ["b1"]]

    def test_the_result_mirrors_the_grouping_it_was_given(self):
        provider = VoyageEmbeddingProvider(
            dimensions=4, transport=_RecordingTransport()
        )
        result = provider.embed_document_chunks([["a1", "a2", "a3"], ["b1"]])

        assert [len(group) for group in result] == [3, 1]
        assert all(len(v) == 4 for group in result for v in group)

    def test_documents_are_sent_as_documents_not_as_queries(self):
        transport = _RecordingTransport()
        VoyageEmbeddingProvider(dimensions=4, transport=transport).embed_document_chunks(
            [["alpha"]]
        )
        assert transport.calls[0][1]["input_type"] == "document"

    def test_a_standalone_text_is_its_own_single_chunk_document(self):
        """A record summary has no siblings. Bundling several records into
        one group to save a request would contextualize each against text it
        has nothing to do with."""
        transport = _RecordingTransport()
        VoyageEmbeddingProvider(dimensions=4, transport=transport).embed_documents(
            ["alpha", "beta"]
        )
        assert transport.calls[0][1]["inputs"] == [["alpha"], ["beta"]]

    def test_embedding_no_documents_makes_no_request(self):
        transport = _RecordingTransport()
        provider = VoyageEmbeddingProvider(dimensions=4, transport=transport)
        assert provider.embed_document_chunks([]) == []
        assert transport.calls == []

    def test_a_document_is_never_split_across_two_requests(self):
        """Splitting one is the one thing the batching rule may not do: half a
        document's chunks in view is not the context the model was chosen
        for, and the resulting vectors look entirely normal."""
        transport = _RecordingTransport()
        provider = VoyageEmbeddingProvider(dimensions=4, transport=transport)
        # Each chunk is ~14k estimated tokens, so two documents of two chunks
        # cannot share one 32k-token request.
        document = [" ".join(["word"] * 10_000) for _ in range(2)]

        result = provider.embed_document_chunks([document, list(document)])

        assert len(transport.calls) == 2, "the two documents shared a request"
        for _, payload in transport.calls:
            assert len(payload["inputs"]) == 1
            assert len(payload["inputs"][0]) == 2, "a document was split"
        assert [len(group) for group in result] == [2, 2]

    def test_a_short_group_raises_rather_than_misaligning_chunks(self):
        provider = VoyageEmbeddingProvider(
            dimensions=4, transport=_RecordingTransport(short_by=1)
        )
        with pytest.raises(VoyageError, match="positionally"):
            provider.embed_document_chunks([["alpha", "beta"]])

    def test_a_missing_document_group_raises_rather_than_shifting_documents(self):
        """One group short and every later document's vectors belong to the
        wrong record — a mislabelling no later stage can detect."""
        provider = VoyageEmbeddingProvider(
            dimensions=4, transport=_RecordingTransport(drop_groups=1)
        )
        with pytest.raises(VoyageError, match="document groups"):
            provider.embed_document_chunks([["a1"], ["b1"]])

    def test_an_empty_document_among_real_ones_raises(self):
        """The endpoint returns no group for it, so accepting one would shift
        every later document's vectors by one."""
        provider = VoyageEmbeddingProvider(
            dimensions=4, transport=_RecordingTransport()
        )
        with pytest.raises(VoyageError, match="no chunks"):
            provider.embed_document_chunks([["a1"], []])


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


class OutputDimensionTests:
    def test_the_adapter_asks_for_exactly_what_the_vector_columns_hold(self):
        """IR-280. The dimension Voyage is asked to emit and the width of the
        column the vector lands in are one number. When they were two settings
        they could disagree, and a 512-vector against a 1024 column is the
        silent-drift bug this ticket closed everywhere else."""
        from apps.ai.models import VECTOR_COLUMN_DIMENSIONS

        transport = _RecordingTransport(dimensions=VECTOR_COLUMN_DIMENSIONS)
        VoyageEmbeddingProvider(transport=transport).embed_documents(["alpha"])

        _, payload = transport.calls[0]
        assert payload["output_dimension"] == VECTOR_COLUMN_DIMENSIONS
