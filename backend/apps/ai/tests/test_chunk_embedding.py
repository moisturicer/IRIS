"""Chunk and record embedding through the provider port (IR-281, ADR-024).

Two things are asserted here that nothing else can assert.

**That the vendor is not called when it need not be.** Every guard in
``apps.ai.indexing`` runs *before* the call, and the only way to show a call
did not happen is to count calls on a provider that records them — a fake
that embeds honestly and keeps a tally, not a mock asserting a sequence.

**That vectors land under the active Embedding Space, keyed by chunk and
space together.** Which is a database fact, so these need a live Postgres and
``db_required`` skips them cleanly where there is none.

The request *shaping* — that chunks reach the wire grouped by document, at
the contextualized endpoint — is asserted next door in
``apps/ai/providers/tests/test_voyage_adapter.py`` against an injected
transport, with no network and no vendor account.
"""

import pytest
from django.utils import timezone

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.indexing import (
    embed_active_chunk_set,
    embed_record_summary,
    estimate_pending_tokens,
    pending_chunks,
)
from apps.ai.models import (
    VECTOR_COLUMN_DIMENSIONS,
    EmbeddingSpace,
    EmbeddingSpaceState,
    RecordEmbedding,
)
from apps.ai.models.chunk import ChunkEmbedding, DocumentChunk
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.repositories import DjangoChunkRepository
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class _CountingEmbedder(DeterministicEmbeddingProvider):
    """A real embedder that remembers how often it was asked.

    Counting *calls* and *chunks* separately, because the two answer
    different questions: whether a run spent anything at all, and whether it
    spent more than it had to.
    """

    def __init__(self, dimensions=VECTOR_COLUMN_DIMENSIONS):
        super().__init__(dimensions=dimensions)
        self.grouped_calls: list[list[list[str]]] = []
        self.flat_calls: list[list[str]] = []

    def embed_document_chunks(self, documents):
        self.grouped_calls.append([list(d) for d in documents])
        return super().embed_document_chunks(documents)

    def embed_documents(self, texts):
        self.flat_calls.append(list(texts))
        return super().embed_documents(texts)

    @property
    def chunks_sent(self) -> int:
        return sum(len(d) for call in self.grouped_calls for d in call)


@pytest.fixture(autouse=True)
def _one_active_space():
    """Exactly one active space, at the width the columns actually hold.

    Migration 0003 seeds one on every fresh test database; these tests want
    a row they can name, so the seeded one is replaced rather than worked
    around.
    """
    EmbeddingSpace.objects.all().delete()
    return EmbeddingSpace.objects.create(
        model_id="voyage-context-4",
        dimensions=VECTOR_COLUMN_DIMENSIONS,
        metric="cosine",
        state=EmbeddingSpaceState.ACTIVE,
    )


@pytest.fixture
def space(_one_active_space):
    return _one_active_space


@pytest.fixture(autouse=True)
def _records_carry_an_embargo_fact(monkeypatch):
    """Stand in for the embargo field IR-250 will add.

    ``Record`` carries none today, and the disclosure policy treats an
    undetermined embargo as an embargo — so **every** record is currently
    refused, and nothing in IRIS can be indexed until that ticket lands. That
    is the correct failure direction for a gate whose purpose is to stop
    content leaving, and it is asserted directly in ``DisclosureGateTests``.

    The rest of this file is about embedding, not about the gate, so it needs
    records the gate lets through. Patching the attribute onto the model is
    the smallest way to get them: the policy adapter already reads it with
    ``getattr``, so this is exactly the shape IR-250 will make real, and no
    production code is bent to accommodate a test.
    """
    monkeypatch.setattr(Record, "embargoed_until", None, raising=False)


def _disclosable_record(**kwargs) -> Record:
    """A record the disclosure policy permits — given the fixture above."""
    record = Record.objects.create(
        title=kwargs.pop("title", "A thesis"),
        abstract=kwargs.pop("abstract", "An abstract about pond sampling."),
        is_ip=False,
        # `dpa_accepted` is a derived property, not a field: consent is the
        # timestamp, and IR-226 made that stamp the only evidence of it.
        dpa_accepted_at=timezone.now(),
        **kwargs,
    )
    return record


def _chunk_set(*texts: str) -> ChunkSet:
    chunks = tuple(
        Chunk(text=t, content=t, context_path=(), sequence=i, token_count=len(t.split()))
        for i, t in enumerate(texts)
    )
    return ChunkSet(
        chunks=chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(),
        content_hash=chunkset_hash(chunks),
    )


def _with_chunks(record: Record, *texts: str):
    return DjangoChunkRepository().save(
        record_id=record.id, extraction_hash="extraction-hash", chunk_set=_chunk_set(*texts)
    )


class ChunkEmbeddingTests:
    def test_a_chunked_record_gets_a_vector_per_chunk_under_the_active_space(
        self, space
    ):
        """The headline: no code path in IRIS had ever written a chunk vector."""
        record = _disclosable_record()
        _with_chunks(record, "alpha passage", "beta passage", "gamma passage")

        outcome = embed_active_chunk_set(record.id, provider=_CountingEmbedder())

        assert outcome.embedded == 3
        rows = ChunkEmbedding.objects.filter(chunk__record=record)
        assert rows.count() == 3
        assert {row.space_id for row in rows} == {space.id}
        assert all(len(row.embedding) == VECTOR_COLUMN_DIMENSIONS for row in rows)

    def test_the_chunks_reach_the_provider_as_one_document_in_reading_order(self):
        """Grouping is the contract (ADR-015): a contextualized embedder that
        is handed loose chunks returns vectors that have lost the context the
        model was chosen for, and look completely normal."""
        record = _disclosable_record()
        _with_chunks(record, "first", "second", "third")
        provider = _CountingEmbedder()

        embed_active_chunk_set(record.id, provider=provider)

        assert provider.grouped_calls == [[["first", "second", "third"]]]

    def test_a_vector_is_computed_from_text_and_not_from_display_content(self):
        """`text` is what a vector is computed from and never changes;
        `content` is what a citation shows a reader. Embedding the second
        would make the vector drift from the passage it indexes."""
        record = _disclosable_record()
        chunks = (
            Chunk(
                text="the indexed words",
                content="the displayed words",
                context_path=(),
                sequence=0,
                token_count=3,
            ),
        )
        DjangoChunkRepository().save(
            record_id=record.id,
            extraction_hash="h",
            chunk_set=ChunkSet(
                chunks=chunks,
                strategy_id="fixed-window",
                options=ChunkingOptions(),
                content_hash=chunkset_hash(chunks),
            ),
        )
        provider = _CountingEmbedder()

        embed_active_chunk_set(record.id, provider=provider)

        assert provider.grouped_calls == [[["the indexed words"]]]

    def test_a_record_with_no_chunk_set_spends_nothing(self):
        record = _disclosable_record()
        provider = _CountingEmbedder()

        outcome = embed_active_chunk_set(record.id, provider=provider)

        assert outcome.embedded == 0
        assert provider.grouped_calls == []


class IdempotencyTests:
    def test_a_second_run_re_embeds_nothing_and_calls_no_vendor(self):
        record = _disclosable_record()
        _with_chunks(record, "alpha", "beta")
        embed_active_chunk_set(record.id, provider=_CountingEmbedder())

        provider = _CountingEmbedder()
        outcome = embed_active_chunk_set(record.id, provider=provider)

        assert provider.grouped_calls == [], "a re-run paid for existing vectors"
        assert (outcome.embedded, outcome.skipped) == (0, 2)
        assert ChunkEmbedding.objects.filter(chunk__record=record).count() == 2

    def test_a_re_chunk_pays_only_for_the_chunks_whose_text_changed(self):
        """The unchanged-text skip has one definition, not two: a surviving
        chunk's vector is carried across by the repository, and "already has
        a row in this space" is what this reads."""
        record = _disclosable_record()
        _with_chunks(record, "alpha", "beta")
        embed_active_chunk_set(record.id, provider=_CountingEmbedder())

        _with_chunks(record, "alpha", "beta rewritten")
        provider = _CountingEmbedder()
        outcome = embed_active_chunk_set(record.id, provider=provider)

        assert provider.chunks_sent == 1, "an unchanged chunk was re-embedded"
        assert outcome.embedded == 1
        assert outcome.skipped == 1

    def test_force_re_embeds_everything(self):
        record = _disclosable_record()
        _with_chunks(record, "alpha", "beta")
        embed_active_chunk_set(record.id, provider=_CountingEmbedder())

        provider = _CountingEmbedder()
        embed_active_chunk_set(record.id, provider=provider, force=True)

        assert provider.chunks_sent == 2

    def test_pending_chunks_is_empty_once_everything_is_embedded(self, space):
        record = _disclosable_record()
        _with_chunks(record, "alpha", "beta")
        assert len(pending_chunks(record.id, space.id)) == 2

        embed_active_chunk_set(record.id, provider=_CountingEmbedder())

        assert pending_chunks(record.id, space.id) == []
        assert estimate_pending_tokens(record.id, space.id) == 0


class SpaceConsistencyTests:
    def test_a_provider_of_the_wrong_width_is_refused_before_the_vendor_call(self):
        """The mistake this catches writes a vector the column *accepts* and
        that means something else — the kind that returns plausible rankings
        forever."""
        from django.core.exceptions import ImproperlyConfigured

        record = _disclosable_record()
        _with_chunks(record, "alpha")
        provider = _CountingEmbedder(dimensions=8)

        with pytest.raises(ImproperlyConfigured, match="8 dimensions"):
            embed_active_chunk_set(record.id, provider=provider)

        assert provider.grouped_calls == []
        assert not ChunkEmbedding.objects.filter(chunk__record=record).exists()

    def test_a_space_that_disagrees_with_the_columns_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        EmbeddingSpace.objects.all().update(state=EmbeddingSpaceState.RETIRED)
        EmbeddingSpace.objects.create(
            model_id="voyage-context-4",
            dimensions=512,
            state=EmbeddingSpaceState.ACTIVE,
        )
        record = _disclosable_record()
        _with_chunks(record, "alpha")
        provider = _CountingEmbedder()

        with pytest.raises(ImproperlyConfigured, match="indexing path"):
            embed_active_chunk_set(record.id, provider=provider)

        assert provider.grouped_calls == []

    def test_a_short_provider_response_raises_rather_than_misattributing(self):
        class _ShortEmbedder(_CountingEmbedder):
            def embed_document_chunks(self, documents):
                groups = super().embed_document_chunks(documents)
                return [group[:-1] for group in groups]

        record = _disclosable_record()
        _with_chunks(record, "alpha", "beta")

        with pytest.raises(ValueError, match="positionally"):
            embed_active_chunk_set(record.id, provider=_ShortEmbedder())

        assert not ChunkEmbedding.objects.filter(chunk__record=record).exists()


class DisclosureGateTests:
    """Embedding sends the document's own words to a commercial vendor, so it
    sits behind the same gate as reranking and answer generation (ADR-015
    §Security Impact)."""

    def test_a_record_the_policy_refuses_is_never_sent(self):
        record = _disclosable_record()
        record.is_ip = True
        record.save(update_fields=["is_ip"])
        _with_chunks(record, "alpha")
        provider = _CountingEmbedder()

        outcome = embed_active_chunk_set(record.id, provider=provider)

        assert outcome.refused
        assert "intellectual property" in outcome.reason
        assert provider.grouped_calls == []
        assert not ChunkEmbedding.objects.filter(chunk__record=record).exists()

    def test_a_record_with_no_embargo_fact_is_refused(self, monkeypatch):
        """IR-250. `Record` carries no embargo field, so the policy cannot
        determine one and treats it as an embargo. Asserted rather than
        worked around: it is why a real corpus cannot be indexed yet, and it
        should fail loudly the day someone changes the default."""
        monkeypatch.delattr(Record, "embargoed_until", raising=False)
        record = Record.objects.create(
            title="A thesis",
            abstract="An abstract.",
            is_ip=False,
            dpa_accepted_at=timezone.now(),
        )
        _with_chunks(record, "alpha")
        provider = _CountingEmbedder()

        outcome = embed_active_chunk_set(record.id, provider=provider)

        assert outcome.refused
        assert "embargo" in outcome.reason
        assert provider.grouped_calls == []


class RecordSummaryTests:
    def test_a_record_summary_is_embedded_in_process_with_no_gateway(self, space):
        """ADR-024. The gateway call this replaces posted to a route that was
        never registered, at an endpoint that returns no vector field."""
        record = _disclosable_record(title="Pond sampling", abstract="Weekly.")
        provider = _CountingEmbedder()

        outcome = embed_record_summary(record.id, provider=provider)

        assert outcome.embedded == 1
        assert provider.flat_calls == [["Pond sampling. Weekly."]]
        row = RecordEmbedding.objects.get(record=record)
        assert len(row.embedding) == VECTOR_COLUMN_DIMENSIONS
        assert row.model_name == space.model_id

    def test_a_refused_record_gets_no_summary_vector(self):
        record = _disclosable_record()
        record.is_ip = True
        record.save(update_fields=["is_ip"])
        provider = _CountingEmbedder()

        outcome = embed_record_summary(record.id, provider=provider)

        assert outcome.refused
        assert provider.flat_calls == []
        assert not RecordEmbedding.objects.filter(record=record).exists()

    def test_the_task_path_re_embeds_because_it_was_queued_by_a_change(self):
        record = _disclosable_record()
        embed_record_summary(record.id, provider=_CountingEmbedder())

        provider = _CountingEmbedder()
        embed_record_summary(record.id, provider=provider)

        assert provider.flat_calls != []

    def test_a_backfill_skips_a_record_already_embedded_under_this_space(self):
        record = _disclosable_record()
        embed_record_summary(record.id, provider=_CountingEmbedder())

        provider = _CountingEmbedder()
        outcome = embed_record_summary(record.id, provider=provider, skip_existing=True)

        assert provider.flat_calls == []
        assert (outcome.embedded, outcome.skipped) == (0, 1)

