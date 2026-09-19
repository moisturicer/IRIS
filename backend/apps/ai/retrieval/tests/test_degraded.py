"""Degrading to full-text search when the vendor is out (IR-132).

Failure is injected through the port rather than by mocking a call sequence:
what matters is that an unreachable vendor produces keyword results and a flag,
not which method was called in which order.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkSet, DocumentChunk
from apps.ai.resilience.circuit import CircuitOpen
from apps.ai.resilience.rate_limit import RateLimited
from apps.ai.retrieval.degraded import (
    DegradableRetriever,
    FullTextRetriever,
)
from apps.ai.retrieval.ports import RetrievedChunk, Retriever
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

User = get_user_model()
DIMENSIONS = VECTOR_COLUMN_DIMENSIONS


class _Failing(Retriever):
    def __init__(self, exception):
        self._exception = exception

    def retrieve(self, question, user, limit=20):
        raise self._exception


class _Healthy(Retriever):
    def __init__(self, chunks=()):
        self._chunks = list(chunks)

    def retrieve(self, question, user, limit=20):
        return self._chunks[:limit]


@pytest.fixture
def reader(db):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=ROLE_STUDENT)[0]
    return User.objects.create_user(
        email="reader@cit.edu", password="x", role=role, is_verified=True
    )


def make_record(title, owner, texts, *, status=PipelineStatus.PUBLISHED):
    record = Record.objects.create(title=title, pipeline_status=status)
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash="h", strategy_id="s",
        options={}, content_hash=f"c{record.pk}", is_active=True,
    )
    for i, text in enumerate(texts):
        DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=i,
            max_sequence=len(texts) - 1, text=text, content=text,
            context_path=[title], token_count=len(text.split()),
            text_hash=f"h{record.pk}{i}", source_page=1,
            element_kinds=["paragraph"], bboxes=[],
        )
    return record


class FullTextFallbackTests:
    def test_it_finds_a_chunk_by_keyword(self, reader):
        make_record("Thesis", reader, ["weekly pond sampling procedure"])

        results = FullTextRetriever().retrieve("sampling", reader)

        assert [r.content for r in results] == ["weekly pond sampling procedure"]

    def test_it_marks_its_results_degraded(self, reader):
        make_record("Thesis", reader, ["weekly pond sampling"])
        assert FullTextRetriever().retrieve("sampling", reader).degraded is True

    def test_it_applies_the_same_visibility_predicate_as_the_vector_path(self, reader):
        """The answer must not depend on whether the vendor happened to be up.
        `apps/ai/services/retrieval.py` filters on `publicly_visible()`, which
        is a different, narrower rule -- reusing it here would put a second
        visibility definition on the retrieval path."""
        from apps.accounts.models import Role

        role = Role.objects.get_or_create(name=ROLE_STUDENT)[0]
        stranger = User.objects.create_user(
            email="stranger@cit.edu", password="x", role=role, is_verified=True
        )
        make_record("Draft", reader, ["weekly pond sampling"],
                    status=PipelineStatus.DRAFT)

        assert FullTextRetriever().retrieve("sampling", stranger) == []
        assert len(FullTextRetriever().retrieve("sampling", reader)) == 1

    def test_only_the_active_chunk_set_is_searched(self, reader):
        record = make_record("Thesis", reader, ["the current passage"])
        superseded = ChunkSet.objects.create(
            record=record, extraction_hash="h2", strategy_id="s",
            options={}, content_hash="old", is_active=False,
        )
        DocumentChunk.objects.create(
            chunk_set=superseded, record=record, sequence=0, max_sequence=0,
            text="the superseded passage", content="the superseded passage",
            context_path=["Thesis"], token_count=3, text_hash="old0",
            source_page=1, element_kinds=["paragraph"], bboxes=[],
        )

        found = [r.content for r in FullTextRetriever().retrieve("passage", reader)]
        assert found == ["the current passage"]

    def test_an_empty_question_returns_nothing_rather_than_everything(self, reader):
        make_record("Thesis", reader, ["weekly pond sampling"])
        assert FullTextRetriever().retrieve("   ", reader) == []


class DegradationTests:
    def test_an_open_circuit_degrades_rather_than_raising(self, reader):
        make_record("Thesis", reader, ["weekly pond sampling"])

        results = DegradableRetriever(_Failing(CircuitOpen("open"))).retrieve(
            "sampling", reader
        )

        assert [r.content for r in results] == ["weekly pond sampling"]
        assert results.degraded is True

    def test_an_exhausted_rate_limit_degrades_too(self, reader):
        make_record("Thesis", reader, ["weekly pond sampling"])

        results = DegradableRetriever(_Failing(RateLimited("spent"))).retrieve(
            "sampling", reader
        )
        assert results.degraded is True

    def test_a_healthy_path_is_not_marked_degraded(self, reader):
        chunk = RetrievedChunk(
            chunk_id=1, record_id=1, record_title="T", content="c",
            context_path=(), source_page=1, score=1.0,
        )
        results = DegradableRetriever(_Healthy([chunk])).retrieve("q", reader)

        assert results.degraded is False
        assert len(results) == 1

    def test_an_ordinary_bug_is_not_swallowed_as_an_outage(self, reader):
        """Returning keyword results for our own broken query would hide the
        bug behind slightly worse answers, which is how a defect survives a
        release."""
        with pytest.raises(ValueError):
            DegradableRetriever(_Failing(ValueError("bad query"))).retrieve("q", reader)

    def test_the_degraded_result_needs_no_special_case_from_a_caller(self, reader):
        """ADR-008 asks for the same interface, not a second one."""
        make_record("Thesis", reader, ["weekly pond sampling"])
        results = DegradableRetriever(_Failing(CircuitOpen("open"))).retrieve(
            "sampling", reader
        )

        assert isinstance(results, list)
        assert [r.content for r in results][:1] == ["weekly pond sampling"]
        assert isinstance(results[0], RetrievedChunk)
