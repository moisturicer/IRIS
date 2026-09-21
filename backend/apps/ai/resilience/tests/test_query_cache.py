"""Caching query embeddings (IR-132).

The interesting part is the **key**, not the store. Two questions that differ
only in spacing are the same question and should cost one vendor call; the same
question under a different embedding space is a different vector and must never
share an entry.
"""

from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.resilience.query_cache import CachingEmbeddingProvider, query_cache_key


class _CountingEmbedder(DeterministicEmbeddingProvider):
    def __init__(self, dimensions=16):
        super().__init__(dimensions=dimensions)
        self.query_calls = 0
        self.document_calls = 0

    def embed_query(self, text):
        self.query_calls += 1
        return super().embed_query(text)

    def embed_documents(self, texts):
        self.document_calls += 1
        return super().embed_documents(texts)


class KeyTests:
    def test_the_space_id_is_part_of_the_key(self):
        """Mandatory, not defensive: a cached vector from a retired space is a
        cross-space comparison bug that survives a redeploy."""
        assert query_cache_key("a question", space_id=1) != query_cache_key(
            "a question", space_id=2
        )

    def test_questions_differing_only_in_whitespace_share_an_entry(self):
        assert query_cache_key("  weekly   pond sampling ", space_id=1) == (
            query_cache_key("weekly pond sampling", space_id=1)
        )

    def test_questions_differing_only_in_case_share_an_entry(self):
        assert query_cache_key("Weekly Pond Sampling", space_id=1) == (
            query_cache_key("weekly pond sampling", space_id=1)
        )

    def test_different_questions_do_not_collide(self):
        assert query_cache_key("alpha", space_id=1) != query_cache_key("beta", space_id=1)


class CachingTests:
    def test_a_repeated_question_costs_one_vendor_call(self):
        """The assignment case: forty students sent after the same thing."""
        inner = _CountingEmbedder()
        provider = CachingEmbeddingProvider(inner, cache={}, space_id=1)

        for _ in range(40):
            provider.embed_query("weekly pond sampling")

        assert inner.query_calls == 1

    def test_a_cache_hit_returns_the_same_vector(self):
        inner = _CountingEmbedder()
        provider = CachingEmbeddingProvider(inner, cache={}, space_id=1)

        first = provider.embed_query("weekly pond sampling")
        assert provider.embed_query("weekly pond sampling") == first

    def test_the_same_question_under_a_different_space_makes_a_second_call(self):
        inner = _CountingEmbedder()
        cache = {}
        CachingEmbeddingProvider(inner, cache=cache, space_id=1).embed_query("q")
        CachingEmbeddingProvider(inner, cache=cache, space_id=2).embed_query("q")

        assert inner.query_calls == 2

    def test_documents_are_not_cached(self):
        """A corpus text is embedded once at ingestion and never re-requested,
        so caching it would spend memory to serve nobody -- and the caller
        already has incremental re-chunking to avoid the repeat work."""
        inner = _CountingEmbedder()
        provider = CachingEmbeddingProvider(inner, cache={}, space_id=1)

        provider.embed_documents(["alpha"])
        provider.embed_documents(["alpha"])

        assert inner.document_calls == 2

    def test_dimensions_are_reported_from_the_wrapped_provider(self):
        inner = _CountingEmbedder(dimensions=16)
        assert CachingEmbeddingProvider(inner, cache={}, space_id=1).dimensions == 16
