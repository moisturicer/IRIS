"""Atomic swap and incremental re-chunking (IR-115 G).

The claims under test are budgetary as much as they are about correctness:
an unchanged document must cost zero writes and zero embedding calls, and a
one-paragraph edit must cost one. Everything else here exists to make sure
that cheapness is not bought by letting retrieval observe a partial state.
"""

import threading

import pytest
from django.conf import settings
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunk_text_hash, chunkset_hash
from apps.ai.models import EmbeddingSpace, EmbeddingSpaceState
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet as ChunkSetModel, DocumentChunk
from apps.ai.repositories import DjangoChunkRepository
from apps.records.models import Record

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _no_seeded_active_space():
    """Migration 0003 seeds one active EmbeddingSpace on every fresh test
    database; the fixture below would otherwise collide with it on the
    partial unique constraint."""
    EmbeddingSpace.objects.all().delete()


@pytest.fixture
def space():
    return EmbeddingSpace.objects.create(
        model_id="voyage-context-4",
        dimensions=settings.AI_EMBEDDING_DIMENSIONS,
        state=EmbeddingSpaceState.ACTIVE,
    )


def _chunk(text: str, sequence: int) -> Chunk:
    return Chunk(
        text=text,
        content=text,
        context_path=("Doc",),
        sequence=sequence,
        token_count=1,
    )


def _set(*texts: str) -> ChunkSet:
    chunks = tuple(_chunk(t, i) for i, t in enumerate(texts))
    return ChunkSet(
        chunks=chunks,
        strategy_id="fixed-window",
        options=ChunkingOptions(),
        content_hash=chunkset_hash(chunks),
    )


def _embed_all(chunk_set_id: int, space: EmbeddingSpace) -> None:
    """Stands in for the embedding stage: gives every chunk of a set a
    distinguishable vector, so carry-over can be checked by value."""
    for i, chunk in enumerate(
        DocumentChunk.objects.filter(chunk_set_id=chunk_set_id).order_by("sequence")
    ):
        vector = [0.0] * settings.AI_EMBEDDING_DIMENSIONS
        vector[0] = float(i + 1)
        ChunkEmbedding.objects.create(chunk=chunk, space=space, embedding=vector)


class TestAtomicSwap:
    def test_the_database_rejects_a_second_active_chunk_set(self):
        """The invariant is enforced by a partial unique index, not by
        application code a future caller could bypass."""
        record = Record.objects.create(title="Two actives")
        DjangoChunkRepository().rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha")
        )

        with pytest.raises(IntegrityError):
            ChunkSetModel.objects.create(
                record_id=record.id,
                extraction_hash="e2",
                strategy_id="fixed-window",
                options={},
                content_hash="x",
                is_active=True,
            )

    def test_a_swap_deactivates_the_old_set_rather_than_deleting_it(self):
        record = Record.objects.create(title="Swap")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha")
        ).chunk_set

        second = repo.rechunk(
            record_id=record.id, extraction_hash="e2", chunk_set=_set("beta")
        ).chunk_set

        assert first.id != second.id
        assert ChunkSetModel.objects.get(pk=first.id).is_active is False
        assert ChunkSetModel.objects.get(pk=second.id).is_active is True
        assert ChunkSetModel.objects.filter(record_id=record.id).count() == 2

    def test_exactly_one_set_is_active_at_every_committed_point(self):
        """A reader never observes zero or two: the deactivate and the
        insert are one transaction, and the index forbids the two case."""
        record = Record.objects.create(title="Never two")
        repo = DjangoChunkRepository()
        for i, text in enumerate(["alpha", "beta", "gamma"]):
            repo.rechunk(
                record_id=record.id, extraction_hash=f"e{i}", chunk_set=_set(text)
            )
            assert (
                ChunkSetModel.objects.filter(
                    record_id=record.id, is_active=True
                ).count()
                == 1
            )

    @pytest.mark.django_db(transaction=True)
    def test_a_concurrent_reader_never_observes_zero_or_two(self, monkeypatch):
        """The sequential test above proves the index; this one proves the
        transaction. A second connection reads the record mid-swap — after
        the deactivate and the insert, before the commit — and must still
        see exactly the superseded set, because neither statement is
        visible to it yet."""
        record = Record.objects.create(title="Concurrent reader")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha")
        ).chunk_set

        observed: list[list[int]] = []

        def read_on_another_connection() -> list[int]:
            """A thread gets its own database connection, so this read is
            genuinely outside the swap's transaction rather than inside it."""
            seen: list[list[int]] = []

            def work():
                try:
                    seen.append(
                        list(
                            ChunkSetModel.objects.filter(
                                record_id=record.id, is_active=True
                            ).values_list("id", flat=True)
                        )
                    )
                finally:
                    connection.close()

            reader = threading.Thread(target=work)
            reader.start()
            reader.join(timeout=10)
            assert seen, "the concurrent reader blocked or failed"
            return seen[0]

        real_bulk_create = DocumentChunk.objects.bulk_create

        def peek(*args, **kwargs):
            rows = real_bulk_create(*args, **kwargs)
            observed.append(read_on_another_connection())
            return rows

        monkeypatch.setattr(DocumentChunk.objects, "bulk_create", peek)
        second = repo.rechunk(
            record_id=record.id, extraction_hash="e2", chunk_set=_set("beta")
        ).chunk_set

        assert observed == [[first.id]]
        assert list(
            ChunkSetModel.objects.filter(
                record_id=record.id, is_active=True
            ).values_list("id", flat=True)
        ) == [second.id]

    def test_a_failed_swap_leaves_the_previous_set_active(self, monkeypatch):
        record = Record.objects.create(title="Rollback")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha")
        ).chunk_set

        def boom(*args, **kwargs):
            raise RuntimeError("the embedding provider fell over")

        monkeypatch.setattr(DocumentChunk.objects, "bulk_create", boom)
        with pytest.raises(RuntimeError):
            repo.rechunk(
                record_id=record.id, extraction_hash="e2", chunk_set=_set("beta")
            )

        active = ChunkSetModel.objects.filter(record_id=record.id, is_active=True)
        assert [s.id for s in active] == [first.id]


class TestNoOpOnUnchangedContent:
    def test_re_running_on_an_unchanged_document_performs_zero_writes(self):
        record = Record.objects.create(title="Idempotent")
        repo = DjangoChunkRepository()
        repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha", "beta")
        )

        with CaptureQueriesContext(connection) as queries:
            outcome = repo.rechunk(
                record_id=record.id,
                extraction_hash="e1",
                chunk_set=_set("alpha", "beta"),
            )

        assert outcome.unchanged is True
        assert outcome.to_embed_count == 0
        written = [
            q["sql"]
            for q in queries.captured_queries
            if q["sql"].strip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}
        ]
        assert written == []

    def test_a_no_op_returns_the_existing_chunk_set(self):
        record = Record.objects.create(title="Idempotent return")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha")
        ).chunk_set

        again = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha")
        ).chunk_set

        assert again.id == first.id
        assert again.chunk_set == first.chunk_set

    def test_a_no_op_keeps_every_vector(self, space):
        record = Record.objects.create(title="Idempotent vectors")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha")
        ).chunk_set
        _embed_all(first.id, space)

        repo.rechunk(record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha"))

        assert ChunkEmbedding.objects.count() == 1


class TestIncrementalReChunk:
    def test_one_edited_paragraph_re_embeds_only_that_paragraph(self, space):
        record = Record.objects.create(title="Typo fix")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id,
            extraction_hash="e1",
            chunk_set=_set("alpha", "beta", "gamma"),
        ).chunk_set
        _embed_all(first.id, space)

        outcome = repo.rechunk(
            record_id=record.id,
            extraction_hash="e2",
            chunk_set=_set("alpha", "BETA", "gamma"),
        )

        assert outcome.to_embed_count == 1
        assert outcome.reused == 2
        assert [c.text for c in outcome.to_embed] == ["BETA"]

    def test_reused_chunks_keep_their_existing_vectors(self, space):
        record = Record.objects.create(title="Vector carry-over")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha", "beta")
        ).chunk_set
        _embed_all(first.id, space)
        original = {
            e.chunk.text_hash: list(e.embedding)
            for e in ChunkEmbedding.objects.select_related("chunk")
        }

        second = repo.rechunk(
            record_id=record.id, extraction_hash="e2", chunk_set=_set("alpha", "BETA")
        ).chunk_set

        carried = list(
            ChunkEmbedding.objects.select_related("chunk").filter(
                chunk__chunk_set_id=second.id
            )
        )
        assert [c.chunk.text for c in carried] == ["alpha"]
        assert list(carried[0].embedding) == original[chunk_text_hash(_chunk("alpha", 0))]

    def test_a_chunk_that_only_moves_keeps_its_vector(self, space):
        record = Record.objects.create(title="Shift")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha", "beta")
        ).chunk_set
        _embed_all(first.id, space)

        outcome = repo.rechunk(
            record_id=record.id,
            extraction_hash="e2",
            chunk_set=_set("preamble", "alpha", "beta"),
        )

        assert outcome.to_embed_count == 1
        assert (
            ChunkEmbedding.objects.filter(
                chunk__chunk_set_id=outcome.chunk_set.id
            ).count()
            == 2
        )

    def test_a_first_chunking_embeds_everything(self):
        record = Record.objects.create(title="First")

        outcome = DjangoChunkRepository().rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha", "beta")
        )

        assert outcome.reused == 0
        assert outcome.to_embed_count == 2

    def test_removed_chunks_are_soft_deleted_not_hard_deleted(self, space):
        record = Record.objects.create(title="Soft delete")
        repo = DjangoChunkRepository()
        first = repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha", "beta")
        ).chunk_set
        _embed_all(first.id, space)
        removed_id = DocumentChunk.objects.get(chunk_set_id=first.id, text="beta").id

        outcome = repo.rechunk(
            record_id=record.id, extraction_hash="e2", chunk_set=_set("alpha")
        )

        assert outcome.soft_deleted == 1
        removed = DocumentChunk.objects.get(pk=removed_id)
        assert removed.deleted_at is not None
        assert (
            DocumentChunk.objects.get(chunk_set_id=first.id, text="alpha").deleted_at
            is None
        )

    def test_a_reinstated_chunk_is_not_left_tombstoned(self):
        """A paragraph deleted and then restored must come back untombstoned,
        or deleted_at stops meaning "no longer in the active chunking"."""
        record = Record.objects.create(title="Undelete")
        repo = DjangoChunkRepository()
        repo.rechunk(
            record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha", "beta")
        )
        repo.rechunk(record_id=record.id, extraction_hash="e2", chunk_set=_set("alpha"))

        repo.rechunk(
            record_id=record.id, extraction_hash="e3", chunk_set=_set("alpha", "beta")
        )

        active = ChunkSetModel.objects.get(record_id=record.id, is_active=True)
        assert (
            DocumentChunk.objects.filter(
                chunk_set=active, deleted_at__isnull=True
            ).count()
            == 2
        )


class TestPublishedRecords:
    def test_a_published_record_can_be_re_chunked(self):
        """Chunking is an index concern, not a record-state concern. The
        repository never consults pipeline_status, and this is the test that
        says the omission is deliberate rather than an oversight."""
        record = Record.objects.create(
            title="Published thesis", pipeline_status="published"
        )
        repo = DjangoChunkRepository()
        repo.rechunk(record_id=record.id, extraction_hash="e1", chunk_set=_set("alpha"))

        outcome = repo.rechunk(
            record_id=record.id, extraction_hash="e2", chunk_set=_set("alpha", "beta")
        )

        assert outcome.to_embed_count == 1
        record.refresh_from_db()
        assert record.pipeline_status == "published"
