"""What two-stage retrieval returns, given that it is allowed to (IR-129).

The visibility guarantee is asserted next door in `test_visibility.py`; this
covers ranking, limits, and which chunks are eligible at all.

No test here reaches inside the cascade to check that stage 1 ran before
stage 2, or what SQL was emitted. Those are implementation and must stay free
to change; the contract is question and user in, ranked permitted chunks out.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

User = get_user_model()
DIMENSIONS = VECTOR_COLUMN_DIMENSIONS


@pytest.fixture
def embedder():
    return DeterministicEmbeddingProvider(dimensions=DIMENSIONS)


@pytest.fixture
def space(db):
    existing = EmbeddingSpace.objects.filter(state="active").first()
    return existing or EmbeddingSpace.objects.create(
        model_id="fake-test", dimensions=DIMENSIONS, metric="cosine", state="active"
    )


@pytest.fixture
def reader(db):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=ROLE_STUDENT)[0]
    return User.objects.create_user(
        email="reader@cit.edu", password="x", role=role, is_verified=True
    )


def published_record(title, owner, embedder):
    record = Record.objects.create(title=title, pipeline_status=PipelineStatus.PUBLISHED)
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    RecordEmbedding.objects.create(
        record=record,
        embedding=embedder.embed_documents([title])[0],
        model_name="fake-test",
    )
    return record


def add_chunks(record, space, embedder, texts, *, active=True, deleted=False):
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash="h", strategy_id="s",
        options={}, content_hash=f"c{record.pk}{active}", is_active=active,
    )
    made = []
    for i, text in enumerate(texts):
        chunk = DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=i,
            max_sequence=len(texts) - 1, text=text, content=text,
            context_path=[record.title], token_count=len(text.split()),
            text_hash=f"h{record.pk}{i}{active}", source_page=1,
            element_kinds=["paragraph"], bboxes=[],
            deleted_at=timezone.now() if deleted else None,
        )
        ChunkEmbedding.objects.create(
            chunk=chunk, space=space, embedding=embedder.embed_documents([text])[0]
        )
        made.append(chunk)
    return made


class EligibilityTests:
    def test_only_the_active_chunk_set_is_searched(self, embedder, space, reader):
        """A superseded chunking still has rows; serving from it would answer
        from a version of the document that is no longer current."""
        record = published_record("Thesis", reader, embedder)
        add_chunks(record, space, embedder, ["the current passage"], active=True)
        add_chunks(record, space, embedder, ["a superseded passage"], active=False)

        found = [
            p.content
            for p in TwoStageRetriever(embedder).retrieve("passage", reader).passages
        ]
        assert found == ["the current passage"]

    def test_a_soft_deleted_chunk_is_never_returned(self, embedder, space, reader):
        """Incremental re-chunking tombstones removed chunks rather than
        deleting their rows, so retrieval has to honour the tombstone."""
        record = published_record("Thesis", reader, embedder)
        add_chunks(record, space, embedder, ["a removed passage"], deleted=True)

        assert TwoStageRetriever(embedder).retrieve("passage", reader).passages == ()

    def test_nothing_is_returned_when_no_space_is_active(self, embedder, reader):
        """Comparing vectors across spaces returns rows, ranked plausibly, and
        wrong. Returning nothing is the honest answer."""
        published_record("Thesis", reader, embedder)
        EmbeddingSpace.objects.update(state="retired")

        assert TwoStageRetriever(embedder).retrieve("passage", reader).passages == ()


class RankingTests:
    def test_the_closest_passage_ranks_first(self, embedder, space, reader):
        record = published_record("Thesis", reader, embedder)
        add_chunks(
            record, space, embedder,
            ["weekly pond sampling procedure", "unrelated budget narrative"],
        )

        results = TwoStageRetriever(embedder).retrieve(
            "weekly pond sampling procedure", reader
        )
        assert results.passages[0].content == "weekly pond sampling procedure"

    def test_scores_descend(self, embedder, space, reader):
        record = published_record("Thesis", reader, embedder)
        add_chunks(record, space, embedder, ["alpha one", "beta two", "gamma three"])

        scores = [
            p.score
            for p in TwoStageRetriever(embedder).retrieve("alpha", reader).passages
        ]
        assert scores == sorted(scores, reverse=True)

    def test_the_limit_is_honoured(self, embedder, space, reader):
        record = published_record("Thesis", reader, embedder)
        add_chunks(record, space, embedder, [f"passage number {i}" for i in range(10)])

        found = TwoStageRetriever(embedder).retrieve("passage", reader, limit=3)
        assert len(found.passages) == 3

    def test_stage_one_bounds_how_many_records_stage_two_searches(
        self, embedder, space, reader
    ):
        """The reason chunk search is affordable: stage 2 only ever looks
        inside the records stage 1 kept."""
        for i in range(5):
            record = published_record(f"Thesis {i}", reader, embedder)
            add_chunks(record, space, embedder, [f"passage from thesis {i}"])

        retriever = TwoStageRetriever(embedder, record_candidates=2)
        record_ids = {
            p.record_id
            for p in retriever.retrieve("passage", reader, limit=50).passages
        }
        assert len(record_ids) <= 2


class RecordScopingTests:
    """A retriever constructed with `record=` never leaves it (IR-298)."""

    def test_a_record_scoped_retriever_returns_only_that_records_chunks(
        self, embedder, space, reader
    ):
        target = published_record("Target Thesis", reader, embedder)
        add_chunks(target, space, embedder, ["weekly pond sampling procedure"])
        other = published_record("Other Thesis", reader, embedder)
        add_chunks(other, space, embedder, ["weekly pond sampling procedure too"])

        found = TwoStageRetriever(embedder, record=target).retrieve(
            "pond sampling", reader
        )

        assert {p.record_id for p in found.passages} == {target.pk}

    def test_scoping_to_a_record_the_caller_cannot_read_returns_nothing(
        self, embedder, space, reader
    ):
        """The scope is applied through `visible_to`, not instead of it --
        the same fail-closed check every other retrieval path makes."""
        from apps.accounts.models import Role

        role = Role.objects.get_or_create(name=ROLE_STUDENT)[0]
        owner = User.objects.create_user(
            email="owner@cit.edu", password="x", role=role, is_verified=True
        )
        hidden = Record.objects.create(
            title="Hidden Draft", pipeline_status=PipelineStatus.DRAFT
        )
        RecordOwner.objects.create(record=hidden, user=owner, is_primary=True)
        RecordEmbedding.objects.create(
            record=hidden,
            embedding=embedder.embed_documents(["Hidden Draft"])[0],
            model_name="fake-test",
        )
        add_chunks(hidden, space, embedder, ["a secret finding"])

        found = TwoStageRetriever(embedder, record=hidden).retrieve(
            "finding", reader
        )

        assert found.passages == ()

    def test_an_unscoped_retriever_reaches_every_readable_record(
        self, embedder, space, reader
    ):
        first = published_record("First Thesis", reader, embedder)
        add_chunks(first, space, embedder, ["weekly pond sampling procedure"])
        second = published_record("Second Thesis", reader, embedder)
        add_chunks(second, space, embedder, ["weekly pond sampling procedure too"])

        found = TwoStageRetriever(embedder).retrieve("pond sampling", reader)

        assert {p.record_id for p in found.passages} == {first.pk, second.pk}


class ResultShapeTests:
    def test_a_result_carries_what_a_citation_needs(self, embedder, space, reader):
        record = published_record("Tilapia Feed Study", reader, embedder)
        add_chunks(record, space, embedder, ["weekly pond sampling"])

        result = TwoStageRetriever(embedder).retrieve("sampling", reader).passages[0]
        assert result.record_id == record.pk
        assert result.record_title == "Tilapia Feed Study"
        assert result.source_page == 1
        assert result.context_path == ("Tilapia Feed Study",)
        assert result.chunk_id
