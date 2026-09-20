"""Indexing a corpus without an accident, and promoting only what is ready
(IR-282).

Four things the ticket asks to be demonstrated rather than asserted in a
docstring: the ceiling refuses, an interrupted run resumes, an unchanged
chunk is not paid for twice, and an incomplete Embedding Space cannot go
live.

Every test runs against the deterministic fake and a real Postgres. There is
no corpus yet (IR-278) and no vendor account is needed, which is the point:
a spend guard that only runs where a paid key is configured is a spend guard
that does not run.
"""

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.ai.backfill import plan_records, record_has_only_stub_documents
from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.indexing import embed_active_chunk_set
from apps.ai.models import (
    VECTOR_COLUMN_DIMENSIONS,
    EmbeddingSpace,
    EmbeddingSpaceState,
)
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.promotion import PromotionRefused, promote, records_missing_vectors
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.repositories import DjangoChunkRepository
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class _CountingEmbedder(DeterministicEmbeddingProvider):
    def __init__(self, dimensions=VECTOR_COLUMN_DIMENSIONS, fail_on=()):
        super().__init__(dimensions=dimensions)
        self.chunks_sent = 0
        self._fail_on = set(fail_on)

    def embed_document_chunks(self, documents):
        for document in documents:
            if any(text in self._fail_on for text in document):
                raise RuntimeError("the vendor fell over")
            self.chunks_sent += len(document)
        return super().embed_document_chunks(documents)


@pytest.fixture(autouse=True)
def _one_active_space():
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
    """Stand in for the field IR-250 will add — see the note in
    ``test_chunk_embedding.py``. Without it the gate refuses every record and
    a backfill has nothing to demonstrate."""
    monkeypatch.setattr(Record, "embargoed_until", None, raising=False)


@pytest.fixture(autouse=True)
def _deterministic_provider(monkeypatch):
    """No vendor, ever, from a command's own composition.

    The commands build their provider through ``build_embedding_provider``;
    patching that one function is what keeps a test from needing a key, and
    is why that function exists rather than a module-level instance.
    """
    monkeypatch.setattr(
        "apps.ai.indexing.build_embedding_provider",
        lambda: DeterministicEmbeddingProvider(dimensions=VECTOR_COLUMN_DIMENSIONS),
    )


def _record(title="A thesis", chunks=("alpha", "beta")) -> Record:
    record = Record.objects.create(
        title=title,
        abstract="An abstract.",
        is_ip=False,
        dpa_accepted_at=timezone.now(),
    )
    if chunks:
        _chunk(record, *chunks)
    return record


def _chunk(record: Record, *texts: str):
    values = tuple(
        Chunk(text=t, content=t, context_path=(), sequence=i, token_count=len(t.split()))
        for i, t in enumerate(texts)
    )
    DjangoChunkRepository().save(
        record_id=record.id,
        extraction_hash="extraction-hash",
        chunk_set=ChunkSet(
            chunks=values,
            strategy_id="fixed-window",
            options=ChunkingOptions(),
            content_hash=chunkset_hash(values),
        ),
    )


class PreFlightEstimateTests:
    def test_the_plan_counts_only_what_is_still_pending(self, space):
        record = _record()

        before = plan_records([record], space_id=space.id)
        assert before.chunk_count == 2
        assert before.estimated_tokens > 0

        embed_active_chunk_set(record.id, provider=_CountingEmbedder())

        after = plan_records([Record.objects.get(pk=record.id)], space_id=space.id)
        assert after.chunk_count == 0
        assert after.estimated_tokens == 0
        assert after.skipped[0].reason == "already embedded in this space"

    def test_the_cost_is_derived_from_the_token_estimate(self, space):
        record = _record()
        plan = plan_records([record], space_id=space.id, cost_per_million=10.0)
        assert plan.estimated_cost == pytest.approx(
            plan.estimated_tokens * 10.0 / 1_000_000
        )

    def test_a_dry_run_sends_nothing(self, space, capsys):
        record = _record()

        call_command("backfill_embeddings", "--dry-run")

        assert "Dry run" in capsys.readouterr().out
        assert not ChunkEmbedding.objects.filter(chunk__record=record).exists()


class TokenCeilingTests:
    def test_a_plan_over_the_ceiling_refuses_to_start(self, space):
        record = _record()

        with pytest.raises(CommandError, match="over the ceiling"):
            call_command("backfill_embeddings", "--token-ceiling", "1")

        assert not ChunkEmbedding.objects.filter(chunk__record=record).exists()

    def test_the_refusal_happens_before_anything_is_sent(self, space, capsys):
        _record()
        with pytest.raises(CommandError, match="Nothing has been sent"):
            call_command("backfill_embeddings", "--token-ceiling", "1")

    def test_a_ceiling_of_zero_disables_the_guard(self, space):
        record = _record()

        call_command("backfill_embeddings", "--token-ceiling", "0")

        assert ChunkEmbedding.objects.filter(chunk__record=record).count() == 2


class ResumeAndIdempotencyTests:
    def test_a_run_interrupted_partway_resumes_where_it_stopped(self, space):
        """No checkpoint file: what the run embeds is recomputed from the
        database each time, so the resume is a property of the query rather
        than of bookkeeping that could itself be lost in the crash."""
        first = _record(title="First", chunks=("alpha", "beta"))
        second = _record(title="Second", chunks=("gamma", "delta"))

        # The first record succeeds; the second falls over mid-run.
        embed_active_chunk_set(first.id, provider=_CountingEmbedder())
        with pytest.raises(RuntimeError):
            embed_active_chunk_set(
                second.id, provider=_CountingEmbedder(fail_on=("gamma",))
            )

        plan = plan_records(
            Record.objects.order_by("pk"), space_id=space.id
        )
        assert [item.record_id for item in plan.to_embed] == [second.id]

        call_command("backfill_embeddings")

        assert ChunkEmbedding.objects.filter(chunk__record=first).count() == 2
        assert ChunkEmbedding.objects.filter(chunk__record=second).count() == 2

    def test_a_second_complete_run_embeds_nothing(self, space, capsys):
        _record()
        call_command("backfill_embeddings")
        capsys.readouterr()

        call_command("backfill_embeddings")

        assert "Nothing to embed" in capsys.readouterr().out

    def test_a_chunk_whose_text_did_not_change_is_not_re_embedded(self, space):
        record = _record(chunks=("alpha", "beta"))
        call_command("backfill_embeddings")

        _chunk(record, "alpha", "beta rewritten")
        plan = plan_records([Record.objects.get(pk=record.id)], space_id=space.id)

        assert plan.chunk_count == 1, "an unchanged chunk was re-planned"

    def test_one_records_failure_does_not_abandon_the_rest(self, space, monkeypatch, capsys):
        good = _record(title="Good", chunks=("alpha",))
        bad = _record(title="Bad", chunks=("explode",))

        monkeypatch.setattr(
            "apps.ai.indexing.build_embedding_provider",
            lambda: _CountingEmbedder(fail_on=("explode",)),
        )
        call_command("backfill_embeddings")

        out = capsys.readouterr().out
        assert "the vendor fell over" in out
        assert f"record {bad.id}" in out
        assert ChunkEmbedding.objects.filter(chunk__record=good).count() == 1
        assert not ChunkEmbedding.objects.filter(chunk__record=bad).exists()


class StubUploadTests:
    def test_a_record_whose_only_document_is_a_placeholder_is_named_as_such(self, space):
        """The 4,910 stubs are skipped by construction — they never extracted,
        so there is no chunk set. The point of this is that the report *says
        so*: five thousand silently absent records look exactly like a broken
        run."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.documents.models import RecordUpload, UploadSlot
        from apps.records.models import RecordType

        record_type, _ = RecordType.objects.get_or_create(name="Thesis / Research")
        record = Record.objects.create(
            title="Stub only",
            record_type=record_type,
            dpa_accepted_at=timezone.now(),
        )
        slot = UploadSlot.objects.create(name="Manuscript", record_type=record_type)
        RecordUpload.objects.create(
            record=record,
            slot=slot,
            file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
        )

        assert record_has_only_stub_documents(record)

        plan = plan_records([record], space_id=space.id)
        assert plan.stub_records == 1
        assert plan.skipped[0].reason == "placeholder upload, never extracted"

    def test_a_record_with_no_documents_at_all_is_not_called_a_stub(self, space):
        """Unsubmitted and placeholder are different problems, and a label
        that says 'expected' would hide the first behind the second."""
        record = Record.objects.create(title="Nothing uploaded")

        assert not record_has_only_stub_documents(record)

        plan = plan_records([record], space_id=space.id)
        assert plan.stub_records == 0
        assert plan.skipped[0].reason == "no active chunk set"


class PromotionTests:
    @pytest.fixture
    def pending(self):
        return EmbeddingSpace.objects.create(
            model_id="voyage-context-4",
            dimensions=VECTOR_COLUMN_DIMENSIONS,
            state=EmbeddingSpaceState.PENDING,
        )

    def test_promotion_refuses_while_a_record_is_short(self, pending):
        record = _record(chunks=("alpha", "beta"))

        shortfalls = records_missing_vectors(pending.id)
        assert [s.record_id for s in shortfalls] == [record.id]
        assert shortfalls[0].missing == 2 and shortfalls[0].total == 2

        with pytest.raises(PromotionRefused, match="half-indexed"):
            promote(pending)

        pending.refresh_from_db()
        assert pending.state == EmbeddingSpaceState.PENDING

    def test_a_partly_filled_space_is_still_refused(self, pending):
        """The dangerous case is not an empty space — someone would notice
        that. It is one that is nearly complete and ranks confidently over
        the part it holds."""
        record = _record(chunks=("alpha", "beta"))
        embed_active_chunk_set(
            record.id, provider=_CountingEmbedder(), space_id=pending.id
        )
        ChunkEmbedding.objects.filter(space=pending).first().delete()

        with pytest.raises(PromotionRefused):
            promote(pending)

    def test_a_complete_space_promotes_and_retires_the_previous_one(
        self, space, pending
    ):
        record = _record(chunks=("alpha", "beta"))
        embed_active_chunk_set(
            record.id, provider=_CountingEmbedder(), space_id=pending.id
        )

        promote(pending)

        pending.refresh_from_db()
        space.refresh_from_db()
        assert pending.state == EmbeddingSpaceState.ACTIVE
        assert space.state == EmbeddingSpaceState.RETIRED, "superseded, not deleted"

    def test_nothing_promotes_on_its_own_when_a_backfill_finishes(self, space, pending):
        _record(chunks=("alpha",))

        call_command("backfill_embeddings")

        pending.refresh_from_db()
        assert pending.state == EmbeddingSpaceState.PENDING

    def test_the_command_refuses_and_names_the_short_records(self, pending, capsys):
        record = _record(chunks=("alpha", "beta"))

        with pytest.raises(CommandError):
            call_command("promote_embedding_space", "--space", str(pending.id))

        out = capsys.readouterr().out
        assert f"record {record.id}" in out
        assert "2 of 2 chunk(s) short" in out

    def test_check_reports_without_promoting(self, pending, capsys):
        _record(chunks=("alpha",))

        call_command("promote_embedding_space", "--space", str(pending.id), "--check")

        pending.refresh_from_db()
        assert pending.state == EmbeddingSpaceState.PENDING

    def test_a_retired_space_is_not_a_place_to_write_new_vectors(self, space):
        from django.core.exceptions import ImproperlyConfigured

        retired = EmbeddingSpace.objects.create(
            model_id="old-model",
            dimensions=VECTOR_COLUMN_DIMENSIONS,
            state=EmbeddingSpaceState.RETIRED,
        )
        record = _record(chunks=("alpha",))

        with pytest.raises(ImproperlyConfigured, match="retired"):
            embed_active_chunk_set(
                record.id, provider=_CountingEmbedder(), space_id=retired.id
            )
