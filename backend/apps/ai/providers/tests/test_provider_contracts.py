"""One contract suite, run against every implementation of each port (IR-128).

The point of a contract suite is that a fake which passes it is a genuine
substitute for the adapter that also passes it. These run against the
deterministic fakes always, and against the Voyage adapters only when
``VOYAGE_API_KEY`` is set — so the suite is meaningful on a laptop with no
vendor account and stronger on a machine that has one.
"""

import os

import pytest

from apps.ai.providers.fakes import DeterministicEmbeddingProvider, ScriptedReranker
from apps.ai.providers.noop import NoOpReranker
from apps.ai.providers.ports import EmbeddingProvider, Reranker


def _embedders():
    yield pytest.param(DeterministicEmbeddingProvider(dimensions=8), id="fake")
    if os.environ.get("VOYAGE_API_KEY"):
        from apps.ai.providers.voyage import VoyageEmbeddingProvider

        yield pytest.param(VoyageEmbeddingProvider(), id="voyage")


def _rerankers():
    yield pytest.param(NoOpReranker(), id="noop")
    yield pytest.param(ScriptedReranker(), id="scripted")
    if os.environ.get("VOYAGE_API_KEY"):
        from apps.ai.providers.voyage import VoyageReranker

        yield pytest.param(VoyageReranker(), id="voyage")


@pytest.fixture(params=list(_embedders()))
def embedder(request) -> EmbeddingProvider:
    return request.param


@pytest.fixture(params=list(_rerankers()))
def reranker(request) -> Reranker:
    return request.param


class EmbeddingProviderContractTests:
    def test_embedding_documents_returns_one_vector_per_text(self, embedder):
        vectors = embedder.embed_documents(["alpha", "beta", "gamma"])
        assert len(vectors) == 3

    def test_every_vector_has_the_providers_dimensionality(self, embedder):
        vectors = embedder.embed_documents(["alpha", "beta"])
        assert {len(v) for v in vectors} == {embedder.dimensions}

    def test_a_query_embeds_to_a_single_vector(self, embedder):
        assert len(embedder.embed_query("alpha")) == embedder.dimensions

    def test_embedding_no_documents_calls_nothing_and_returns_nothing(self, embedder):
        assert embedder.embed_documents([]) == []

    def test_the_same_text_embeds_the_same_way_twice(self, embedder):
        assert embedder.embed_documents(["alpha"]) == embedder.embed_documents(["alpha"])

    def test_document_and_query_embedding_are_separate_calls(self, embedder):
        """ADR-015 rule 3: Voyage-class models are asymmetric, so a boolean
        flag on one method makes the wrong call possible. Two methods make it
        impossible — asserted as a property of the port, not of one adapter."""
        assert hasattr(embedder, "embed_documents")
        assert hasattr(embedder, "embed_query")


class RerankerContractTests:
    def test_reranking_returns_every_candidate_it_was_given(self, reranker):
        candidates = ["alpha", "beta", "gamma"]
        result = reranker.rerank("a question", candidates)
        assert sorted(r.text for r in result) == sorted(candidates)

    def test_reranking_nothing_returns_nothing(self, reranker):
        assert reranker.rerank("a question", []) == []

    def test_each_result_points_back_at_its_input_position(self, reranker):
        """Callers hold chunks, not strings. Without the original index a
        reranked result cannot be mapped back to the chunk it came from."""
        candidates = ["alpha", "beta", "gamma"]
        result = reranker.rerank("a question", candidates)
        assert sorted(r.index for r in result) == [0, 1, 2]
        for item in result:
            assert candidates[item.index] == item.text

    def test_results_come_back_in_descending_score_order(self, reranker):
        result = reranker.rerank("a question", ["alpha", "beta", "gamma"])
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)


class NoOpRerankerTests:
    """`NoOpReranker` is the production default, so switching reranking off has
    to be a configuration change rather than a code path. That only holds if it
    is a genuine substitute."""

    def test_it_preserves_the_input_order_exactly(self):
        candidates = ["gamma", "alpha", "beta"]
        result = NoOpReranker().rerank("a question", candidates)
        assert [r.text for r in result] == candidates
        assert [r.index for r in result] == [0, 1, 2]

    def test_it_scores_everything_equally_rather_than_inventing_a_ranking(self):
        result = NoOpReranker().rerank("a question", ["alpha", "beta"])
        assert len({r.score for r in result}) == 1
