"""Batching against a token budget, not an item count (IR-128)."""

import pytest

from apps.ai.providers.batching import (
    batch_by_token_budget,
    batch_documents_by_token_budget,
    estimate_tokens,
)


class EstimateTests:
    def test_an_empty_string_costs_nothing(self):
        assert estimate_tokens("") == 0

    def test_it_is_the_tokenizer_the_chunker_counts_with(self):
        """One definition of a token (IR-287).

        This was a words-times-1.4 approximation while the domain carried no
        tokenizer. It carries the real one now, and an estimate that could
        disagree with the chunker was a second source of truth waiting to
        drift -- in the direction that sails past the vendor limit and 400s.
        """
        from apps.ai.chunking.tokens import count_tokens

        text = "Clearance-aware resubmission preserves non-invalidated clearances."
        assert estimate_tokens(text) == count_tokens(text)


class BatchingTests:
    def test_everything_fits_in_one_batch_when_the_budget_allows(self):
        texts = ["alpha", "beta", "gamma"]
        assert batch_by_token_budget(texts, budget=1000) == [texts]

    def test_a_batch_is_closed_before_it_exceeds_the_budget(self):
        texts = ["one two three", "four five six", "seven eight nine"]
        batches = batch_by_token_budget(texts, budget=estimate_tokens(texts[0]) * 2)
        assert len(batches) > 1
        for batch in batches:
            assert sum(estimate_tokens(t) for t in batch) <= estimate_tokens(texts[0]) * 2

    def test_the_rule_is_tokens_not_item_count(self):
        """Many tiny texts belong in one batch; two huge ones do not. An
        item-count rule gets both wrong in opposite directions."""
        tiny = ["a"] * 200
        assert len(batch_by_token_budget(tiny, budget=10_000)) == 1

        huge = [" ".join(["word"] * 500)] * 2
        assert len(batch_by_token_budget(huge, budget=estimate_tokens(huge[0]))) == 2

    def test_an_item_larger_than_the_budget_goes_alone_rather_than_being_split(self):
        """Splitting a text would embed half a passage and silently change what
        the vector means. Sending it alone is the honest failure -- the vendor
        rejects it and says so."""
        oversized = " ".join(["word"] * 5000)
        batches = batch_by_token_budget(["small", oversized, "also small"], budget=100)
        assert [oversized] in batches

    def test_order_is_preserved_and_nothing_is_lost(self):
        texts = [f"text number {i}" for i in range(50)]
        flattened = [t for batch in batch_by_token_budget(texts, budget=40) for t in batch]
        assert flattened == texts

    def test_no_texts_means_no_batches(self):
        assert batch_by_token_budget([], budget=100) == []

    def test_a_non_positive_budget_is_rejected_rather_than_looping_forever(self):
        with pytest.raises(ValueError):
            batch_by_token_budget(["alpha"], budget=0)


class DocumentBatchingTests:
    """IR-281. The contextualized endpoint takes documents, so the batching
    unit is the document — and the one invariant that matters is that a
    document is never split, because half a document's chunks in view is not
    the context the model was chosen for and the vectors look fine either
    way."""

    def test_documents_that_fit_share_one_request(self):
        documents = [["a1", "a2"], ["b1"]]
        assert batch_documents_by_token_budget(documents, budget=10_000) == [documents]

    def test_a_document_is_never_split_even_when_it_exceeds_the_budget(self):
        oversized = [" ".join(["word"] * 5000), " ".join(["word"] * 5000)]
        batches = batch_documents_by_token_budget([oversized], budget=100)
        assert batches == [[oversized]]

    def test_a_document_too_large_to_share_gets_its_own_request(self):
        big = [" ".join(["word"] * 5000)]
        batches = batch_documents_by_token_budget([["small"], big, ["also small"]], budget=100)
        assert [len(batch) for batch in batches] == [1, 1, 1]

    def test_order_is_preserved_at_both_levels(self):
        documents = [[f"doc {d} chunk {c}" for c in range(3)] for d in range(20)]
        flattened = [
            document
            for batch in batch_documents_by_token_budget(documents, budget=40)
            for document in batch
        ]
        assert flattened == documents

    def test_no_documents_means_no_batches(self):
        assert batch_documents_by_token_budget([], budget=100) == []

    def test_a_non_positive_budget_is_rejected(self):
        with pytest.raises(ValueError):
            batch_documents_by_token_budget([["alpha"]], budget=0)
