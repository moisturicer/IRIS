"""The AI Overview reads the whole paper, not a retrieved handful (IR-431).

The record has no vectors, and the root's embedder and reranker raise an
error retrieval does not degrade past, so any retrieval would fail the test.
"""

import pytest
from django.utils import timezone

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.inference import InferenceTask
from apps.ai.models import ChunkSet, DocumentChunk, RecordOverview
from apps.ai.overview import PROMPT_VERSION, overview_for
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import EmbeddingProvider, Reranker
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import DIMENSIONS

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class _FailingEmbedder(EmbeddingProvider):
    @property
    def dimensions(self):
        return DIMENSIONS

    def embed_documents(self, texts):
        raise AssertionError("the overview embedded something")

    def embed_document_chunks(self, documents):
        raise AssertionError("the overview embedded something")

    def embed_query(self, text):
        raise AssertionError("the overview embedded a query")


class _FailingReranker(Reranker):
    def rerank(self, query, documents, top_n=None):
        raise AssertionError("the overview reranked something")


class _TaskRecordingRoot(CompositionRoot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tasks = []

    def llm_for(self, task):
        self.tasks.append(task)
        return super().llm_for(task)


def _root(llm, permits=lambda record: True):
    return _TaskRecordingRoot(
        embedder=_FailingEmbedder(),
        reranker=_FailingReranker(),
        llm=llm,
        permits=permits,
    )


def _chunk(chunk_set, sequence, text, page, **extra):
    return DocumentChunk.objects.create(
        chunk_set=chunk_set, record=chunk_set.record, sequence=sequence,
        max_sequence=2, text=text, content=text,
        context_path=["Paper", f"Section {sequence}"],
        token_count=len(text.split()), text_hash=f"t{chunk_set.pk}-{sequence}",
        source_page=page, element_kinds=["paragraph"], **extra,
    )


@pytest.fixture
def paper():
    """Three active chunks inserted out of order, a soft-deleted one, and an
    older inactive set whose text must never reach the prompt."""
    record = Record.objects.create(
        title="Flood Prediction", abstract="An abstract.",
        pipeline_status=PipelineStatus.PUBLISHED,
    )
    stale = ChunkSet.objects.create(
        record=record, extraction_hash="old", strategy_id="s", options={},
        content_hash="old-hash", is_active=False,
    )
    _chunk(stale, 0, "STALE text from a superseded extraction", 1)

    active = ChunkSet.objects.create(
        record=record, extraction_hash="new", strategy_id="s", options={},
        content_hash="new-hash", is_active=True,
    )
    third = _chunk(active, 2, "THIRD the limitations of the gauge network", 9)
    first = _chunk(active, 0, "FIRST the research objective is flood forecasting", 1)
    second = _chunk(active, 1, "SECOND a convolutional network on rainfall data", 4)
    _chunk(active, 3, "DELETED a chunk withdrawn from the set", 10,
           deleted_at=timezone.now())
    record.chunks = (first, second, third)
    return record


def _prompt(llm):
    [(_system, user)] = llm.calls
    return user


class WholePaperAssemblyTests:
    def test_every_active_chunk_is_sent_in_sequence_order(self, paper):
        llm = ScriptedLLM(reply="An account [1].")

        with use_composition_root(_root(llm)):
            overview_for(paper)

        prompt = _prompt(llm)
        positions = [prompt.index(word) for word in ("FIRST", "SECOND", "THIRD")]
        assert positions == sorted(positions)

    def test_nothing_from_an_inactive_chunk_set_or_a_deleted_chunk(self, paper):
        llm = ScriptedLLM(reply="An account [1].")

        with use_composition_root(_root(llm)):
            overview_for(paper)

        prompt = _prompt(llm)
        assert "STALE" not in prompt
        assert "DELETED" not in prompt

    def test_a_marker_resolves_to_the_chunk_assembled_at_that_number(self, paper):
        llm = ScriptedLLM(reply="The gauge network is sparse [3].")

        with use_composition_root(_root(llm)):
            result = overview_for(paper)

        [citation] = result["overview"]["citations"]
        third = paper.chunks[2]
        assert citation["chunk_id"] == third.pk
        assert citation["page"] == 9


class NoRetrievalTests:
    def test_an_overview_generates_with_no_vectors_and_no_working_retrieval(
        self, paper
    ):
        with use_composition_root(_root(ScriptedLLM(reply="An account [1]."))):
            result = overview_for(paper)

        assert result["state"] == "ready"


class ReusedSeamsTests:
    def test_the_model_is_reached_as_the_summary_task(self, paper):
        root = _root(ScriptedLLM(reply="An account [1]."))

        with use_composition_root(root):
            overview_for(paper)

        assert root.tasks == [InferenceTask.SUMMARY]

    def test_a_record_the_disclosure_gate_refuses_calls_no_model(self, paper):
        llm = ScriptedLLM(reply="An account [1].")

        with use_composition_root(_root(llm, permits=lambda record: False)):
            result = overview_for(paper)

        assert result == {"state": "unavailable", "overview": None}
        assert llm.calls == []
        assert not RecordOverview.objects.filter(record=paper).exists()


class PromptVersionTests:
    def test_a_row_stored_under_the_previous_version_is_regenerated(self, paper):
        RecordOverview.objects.create(
            record=paper, text="From six retrieved passages.", citations=[],
            content_hash="new-hash", prompt_version=PROMPT_VERSION - 1,
        )
        llm = ScriptedLLM(reply="From the whole paper [1].")

        with use_composition_root(_root(llm)):
            result = overview_for(paper)

        assert len(llm.calls) == 1
        assert result["overview"]["text"] == "From the whole paper [1]."
