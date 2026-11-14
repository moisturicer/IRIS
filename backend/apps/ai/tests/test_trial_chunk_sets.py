"""Trial chunk sets (IR-1051): measured beside the live set, never read by it."""

import json
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ai.chunking import ChunkSet as ChunkSetValue
from apps.ai.chunking.document import DocumentElement, NormalizedDocument
from apps.ai.chunking.tokens import TOKENIZER_ID
from apps.ai.composition import use_composition_root
from apps.ai.extraction.serialization import document_to_json
from apps.ai.indexing import embed_active_chunk_set
from apps.ai.ingestion.pipeline import build_chunk_set, default_chunking_options
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.repositories import DjangoChunkRepository
from apps.ai.tests.corpus import make_user, root_with, seed_record_vector
from apps.ai.trials import (
    VariantError,
    build_trial,
    chunking_provenance,
    delete_trial_sets,
    parse_variant,
    plan_trial,
    with_trail,
)
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record
from core.enums import PipelineStatus

METHODS = (
    "We trained a convolutional neural network on rainfall gauge data collected "
    "across twelve stations to predict flooding in the Mananga catchment during "
    "the monsoon season, and compared it with a persistence baseline."
)
RESULTS = (
    "The network anticipated flood peaks six hours earlier than the baseline and "
    "halved the false alarm rate at the downstream gauge in every test year."
)


# -- the variant grammar (no database) ---------------------------------------


def test_a_variant_parses_blank_parts_as_production_and_sorts_options():
    variant = parse_variant("t400=::trail=off,target_tokens=400")
    assert (variant.name, variant.extractor, variant.strategy) == ("t400", "", "")
    assert variant.spec == "::target_tokens=400,trail=off"
    assert variant.trail == "off"


@pytest.mark.parametrize("text", [
    "no-equals", "bad name=::", "x=only:two", "x=::trail=sideways",
    "x=::colour=red", "x=::target_tokens=lots", "x=:nonsense-strategy:",
])
def test_a_malformed_variant_is_refused(text):
    with pytest.raises(VariantError):
        parse_variant(text)


def _value_set():
    document = NormalizedDocument(title="Flood study", elements=_elements())
    return build_chunk_set(document, default_chunking_options())


def _elements():
    return (
        DocumentElement(kind="heading", text="Methods", level=1, page=1),
        DocumentElement(kind="paragraph", text=METHODS, page=1),
        DocumentElement(kind="heading", text="Results", level=1, page=2),
        DocumentElement(kind="paragraph", text=RESULTS, page=2),
    )


def test_trail_off_drops_the_trail_from_what_is_embedded_but_not_what_is_shown():
    built = _value_set()
    off = with_trail(built, "off")
    assert any(c.context_path for c in built.chunks)
    for before, after in zip(built.chunks, off.chunks):
        assert after.context_path == ()
        assert after.content == before.content
        assert " > " not in after.text and not after.text.startswith("Flood study")
    assert off.content_hash != built.content_hash


def test_trail_shuffled_keeps_real_trails_and_is_repeatable():
    built = ChunkSetValue(
        chunks=tuple(
            c.__class__(**{**c.__dict__, "context_path": (f"Section {i}",),
                           "text": f"Section {i}\n\nbody {i}", "sequence": i})
            for i, c in enumerate([_value_set().chunks[0]] * 6)
        ),
        strategy_id="structural", options=default_chunking_options(), content_hash="seed",
    )
    once, twice = with_trail(built, "shuffled"), with_trail(built, "shuffled")
    assert once == twice
    assert sorted(c.context_path for c in once.chunks) == sorted(c.context_path for c in built.chunks)
    assert [c.context_path for c in once.chunks] != [c.context_path for c in built.chunks]
    assert all(c.text.endswith(f"body {c.sequence}") for c in once.chunks)


def test_trail_on_is_the_set_unchanged():
    built = _value_set()
    assert with_trail(built, "on") is built


# -- the corpus -----------------------------------------------------------------


class CountingEmbedder(DeterministicEmbeddingProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunks_sent = 0

    def embed_document_chunks(self, documents):
        self.chunks_sent += sum(len(d) for d in documents)
        return super().embed_document_chunks(documents)


@pytest.fixture
def counting(embedder):
    return CountingEmbedder(dimensions=embedder.dimensions)


def indexed_paper(title, embedder, elements=None):
    """A released paper with a stored extraction, an active set and its vectors."""
    record = Record.objects.create(
        title=title, abstract=f"An abstract for {title}.", is_ip=False, ai_consent=True,
        pipeline_status=PipelineStatus.PUBLISHED, is_embargoed=False,
        embargo_released_at=timezone.now(),
    )
    document = NormalizedDocument(title=title, elements=elements or _elements(),
                                  page_sizes={1: (612.0, 792.0), 2: (612.0, 792.0)})
    PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, status="done", extractor="unstructured",
        structure=document_to_json(document), content_hash=f"x{title}",
    )
    DjangoChunkRepository().rechunk(
        record_id=record.pk, extraction_hash=f"x{title}",
        chunk_set=build_chunk_set(document, default_chunking_options()),
    )
    embed_active_chunk_set(record.pk, provider=embedder)
    seed_record_vector(record=record, embedding=embedder.embed_documents([title])[0],
                       model_name="fake-test")
    return record


def trial_chunk(record, space, embedder, text, variant="probe"):
    """A trial set with one chunk only it holds, vector and all."""
    trial = ChunkSet.objects.create(
        record=record, extraction_hash="x", strategy_id="structural", options={},
        content_hash=f"trial-{record.pk}", trial_variant=variant, trial_spec="::",
    )
    chunk = DocumentChunk.objects.create(
        chunk_set=trial, record=record, sequence=0, max_sequence=0, text=text,
        content=text, text_hash=f"trial-{record.pk}", token_count=len(text.split()),
        source_page=1,
    )
    ChunkEmbedding.objects.create(chunk=chunk, space=space,
                                  embedding=embedder.embed_documents([text])[0])
    return trial


PROBE = "zebracorn migration across the Mananga catchment floodplain"


@pytest.mark.db_required
@pytest.mark.django_db
class TestTrialSetsStayOutOfReaderPaths:
    @pytest.fixture
    def corpus(self, space, embedder):
        record = indexed_paper("Flood prediction in the Mananga catchment", embedder)
        trial_chunk(record, space, embedder, PROBE)
        return record

    @pytest.fixture
    def reader(self):
        return make_user("reader@cit.edu")

    def _contents(self, result):
        return [p.content for p in result.passages]

    def test_a_trial_set_can_never_be_made_active(self, corpus):
        with pytest.raises(IntegrityError), transaction.atomic():
            ChunkSet.objects.filter(trial_variant="probe").update(is_active=True)

    def test_ask_iris_retrieval_never_returns_a_trial_chunk(self, corpus, reader, embedder):
        result = root_with(embedder=embedder).retriever().retrieve(PROBE, reader, limit=20)
        assert result.passages
        assert PROBE not in self._contents(result)

    def test_the_full_text_fallback_never_returns_a_trial_chunk(self, corpus, reader):
        from apps.ai.retrieval.degraded import FullTextRetriever

        assert PROBE not in self._contents(FullTextRetriever().retrieve("zebracorn", reader))

    # The runtime's search tool (Ask IRIS since IR-957) is covered in
    # test_ai_runtime_research_db.py::test_a_trial_chunk_set_is_never_searched_or_read.

    def test_the_status_count_ignores_trial_sets(self, corpus, reader, client_for, space, embedder):
        from django.urls import reverse

        only_trial = Record.objects.create(
            title="Trial only", abstract="", pipeline_status=PipelineStatus.PUBLISHED)
        trial_chunk(only_trial, space, embedder, PROBE, variant="other")
        assert client_for(reader).get(reverse("ai-status")).json()["indexed_records"] == 1

    def test_similarity_reads_no_chunk_set_at_all(self, corpus, reader, embedder):
        from apps.ai.similarity import similar_records

        other = indexed_paper("Rainfall gauges for flood warning", embedder)
        before = [m.record.pk for m in similar_records(other, reader)]
        delete_trial_sets()
        assert [m.record.pk for m in similar_records(other, reader)] == before

    def test_the_ai_overview_is_built_from_the_active_set(self, corpus, embedder):
        from apps.ai.models.summary import RecordOverview
        from apps.ai.overview.service import overview_for

        with use_composition_root(root_with(embedder=embedder)):
            overview_for(corpus)
        active = ChunkSet.objects.get(record=corpus, is_active=True)
        assert RecordOverview.objects.get(record=corpus).content_hash == active.content_hash

    def test_only_a_trial_root_retrieves_from_the_trial_set(self, corpus, reader, embedder):
        trial = root_with(embedder=embedder).for_trial("probe")
        result = trial.retriever().retrieve(PROBE, reader, limit=20)
        assert self._contents(result) == [PROBE]


@pytest.mark.db_required
def test_rolling_back_a_reextraction_never_restores_a_trial_set(db):
    """The rollback picks the newest older inactive set; a trial set is not one."""
    from apps.ai.reextraction import rollback

    record = Record.objects.create(
        title="Rolled back", abstract="An abstract.", is_ip=False, ai_consent=True,
        pipeline_status=PipelineStatus.PUBLISHED, is_embargoed=False,
        embargo_released_at=timezone.now(),
    )
    PdfExtraction.objects.create(record=record, kind=DocumentKind.MANUSCRIPT, status="done",
                                 extractor="llamaparse", content_hash="x")
    ChunkSet.objects.create(record=record, extraction_hash="x", strategy_id="s", options={},
                            content_hash="trial", trial_variant="old", trial_spec="::")
    active = ChunkSet.objects.create(record=record, extraction_hash="x", strategy_id="s",
                                     options={}, content_hash="live", is_active=True)
    assert rollback([record.pk]) == 0
    assert ChunkSet.objects.get(record=record, is_active=True).pk == active.pk


# -- building a variant ---------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class TestBuildingAVariant:
    @pytest.fixture
    def corpus(self, space, embedder):
        return indexed_paper("Flood prediction in the Mananga catchment", embedder)

    def test_a_variant_identical_to_the_active_set_embeds_zero_new_tokens(
        self, corpus, space, counting
    ):
        plan = plan_trial(parse_variant("same=::"), space_id=space.pk)
        assert plan.new_tokens == 0 and plan.new_chunks == 0
        outcome = build_trial(plan, provider=counting)
        assert counting.chunks_sent == 0
        assert outcome.embedded == 0 and outcome.carried == plan.chunk_count
        trial = ChunkSet.objects.get(trial_variant="same")
        assert not trial.is_active
        assert trial.content_hash == ChunkSet.objects.get(record=corpus, is_active=True).content_hash

    def test_trail_off_embeds_only_the_text_that_changed(self, corpus, space, counting):
        plan = plan_trial(parse_variant("off=::trail=off"), space_id=space.pk)
        changed = plan.new_chunks
        assert changed > 0
        build_trial(plan, provider=counting)
        assert counting.chunks_sent == changed
        chunks = DocumentChunk.objects.filter(chunk_set__trial_variant="off")
        assert not chunks.exclude(embeddings__space=space).exists()
        assert ChunkSet.objects.get(record=corpus, is_active=True).trial_variant is None

    def test_a_rebuild_of_the_same_variant_writes_and_sends_nothing(self, corpus, space, counting):
        variant = parse_variant("off=::trail=off")
        build_trial(plan_trial(variant, space_id=space.pk), provider=counting)
        sent = counting.chunks_sent
        again = plan_trial(variant, space_id=space.pk)
        assert again.new_tokens == 0
        outcome = build_trial(again, provider=counting)
        assert (outcome.written, outcome.reused_sets, counting.chunks_sent) == (0, 1, sent)

    def test_a_name_reused_for_another_spec_is_refused(self, corpus, space, counting):
        build_trial(plan_trial(parse_variant("v=::trail=off"), space_id=space.pk),
                    provider=counting)
        with pytest.raises(VariantError, match="already exists"):
            plan_trial(parse_variant("v=::trail=shuffled"), space_id=space.pk)

    def test_another_extractor_is_skipped_by_name_not_reread(self, corpus, space):
        plan = plan_trial(parse_variant("lp=llamaparse::"), space_id=space.pk)
        assert not plan.built
        assert plan.skipped[0].skipped == "stored extraction is unstructured, not llamaparse"

    def test_a_paper_nobody_answered_for_is_not_embedded(self, corpus, space, counting):
        Record.objects.filter(pk=corpus.pk).update(is_embargoed=True, embargo_released_at=None)
        outcome = build_trial(plan_trial(parse_variant("off=::trail=off"), space_id=space.pk),
                              provider=counting)
        assert counting.chunks_sent == 0
        assert corpus.pk in outcome.refused

    def test_provenance_names_extractor_strategy_options_and_tokenizer(self, corpus, space, counting):
        active = chunking_provenance()
        assert active["variant"] is None and active["tokenizer"] == TOKENIZER_ID
        assert [g["extractor"] for g in active["chunk_sets"]] == ["unstructured"]
        variant = parse_variant("off=::trail=off")
        build_trial(plan_trial(variant, space_id=space.pk), provider=counting)
        trial = chunking_provenance(variant)
        assert trial["variant_spec"] == "::trail=off"
        assert trial["chunk_sets"][0]["options"]["trail"] == "off"

    def test_cleanup_removes_trial_sets_and_their_vectors_only(self, corpus, space, counting):
        build_trial(plan_trial(parse_variant("off=::trail=off"), space_id=space.pk),
                    provider=counting)
        live_vectors = ChunkEmbedding.objects.filter(chunk__chunk_set__is_active=True).count()
        call_command("cleanup_trial_chunk_sets", variant="off")
        assert not ChunkSet.objects.filter(trial_variant__isnull=False).exists()
        assert ChunkEmbedding.objects.filter(chunk__chunk_set__is_active=True).count() == live_vectors
        assert ChunkSet.objects.filter(record=corpus, is_active=True).exists()

    def test_cleanup_needs_a_variant_or_all(self, corpus):
        with pytest.raises(CommandError):
            call_command("cleanup_trial_chunk_sets")


# -- the command ------------------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class TestEvalRetrievalVariant:
    TITLE = "Flood prediction in the Mananga catchment"

    @pytest.fixture
    def corpus(self, space, embedder):
        return indexed_paper(self.TITLE, embedder)

    @pytest.fixture
    def questions(self, tmp_path):
        path = tmp_path / "set.json"
        path.write_text(json.dumps({"name": "trial", "questions": [{
            "id": "q1", "question": "how early were flood peaks anticipated?",
            "expected": [{"record": self.TITLE, "quote": "six hours earlier than the baseline"}],
        }]}), encoding="utf-8")
        return path

    def test_dry_run_prints_the_cost_and_writes_nothing(self, corpus, questions, capsys):
        call_command("eval_retrieval", questions=str(questions), variant="off=::trail=off",
                     dry_run=True)
        out = capsys.readouterr().out
        assert "chunks to embed" in out and "new tokens" in out
        assert not ChunkSet.objects.filter(trial_variant__isnull=False).exists()

    def test_a_variant_over_the_ceiling_is_refused_before_anything_is_written(
        self, corpus, questions
    ):
        with pytest.raises(CommandError, match="over the ceiling"):
            call_command("eval_retrieval", questions=str(questions), user="x@cit.edu",
                         variant="off=::trail=off", token_ceiling=1)
        assert not ChunkSet.objects.filter(trial_variant__isnull=False).exists()

    def test_a_variant_run_measures_the_trial_set_and_records_it(
        self, corpus, questions, embedder, tmp_path
    ):
        make_user("reader@cit.edu")
        out = tmp_path / "runs"
        with use_composition_root(root_with(embedder=embedder)):
            call_command("eval_retrieval", questions=str(questions), user="reader@cit.edu",
                         variant="off=::trail=off", reranking="off", out=str(out))
        run = json.loads(next(Path(out).glob("*.json")).read_text(encoding="utf-8"))["runs"][0]
        chunking = run["provenance"]["chunking"]
        assert chunking["variant"] == "off" and chunking["tokenizer"] == TOKENIZER_ID
        assert run["provenance"]["trial"] == {"skipped": {}, "not_embedded": {}}
        assert run["measures"]["recall@10"] == 1.0

    def test_an_active_run_records_its_chunking_too(self, corpus, questions, embedder, tmp_path):
        make_user("reader@cit.edu")
        out = tmp_path / "runs"
        with use_composition_root(root_with(embedder=embedder)):
            call_command("eval_retrieval", questions=str(questions), user="reader@cit.edu",
                         reranking="off", out=str(out))
        run = json.loads(next(Path(out).glob("*.json")).read_text(encoding="utf-8"))["runs"][0]
        assert run["provenance"]["chunking"]["variant"] is None
        assert run["provenance"]["chunking"]["chunk_sets"][0]["strategy_id"]

