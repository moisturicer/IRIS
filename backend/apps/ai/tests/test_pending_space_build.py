"""Building a pending Embedding Space while search stays on the active one
(IR-752, ADR-049 §23, ADR-015).

Two deterministic embedding identities stand in for an old and a new model:
the active space is what readers search, the pending one is built beside it.
What is demonstrated, with a real Postgres and no vendor:

* a build writes only the pending space, so an active vector is never
  overwritten and no reader's result, count or similarity moves;
* the build is bounded, restartable and redeliverable: finished records keep
  their vectors, only the remainder is sent again;
* every attempt re-checks the disclosure gate, the current source and the
  shared admission lane, and an admission refusal stops the run;
* nothing here can activate a space.
"""

import pathlib

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.ai.admission.errors import AdmissionDenied, CAMPAIGN_EXHAUSTED
from apps.ai.admission.scope import lane_for
from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.indexing import embed_record_summary
from apps.ai.models import (
    VECTOR_COLUMN_DIMENSIONS,
    EmbeddingSpace,
    EmbeddingSpaceState,
    RecordEmbedding,
)
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.models.embedding import RecordSpaceEmbedding
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.repositories import DjangoChunkRepository
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.ai.similarity import similar_records
from apps.ai.space_build import (
    BuildRefused,
    build_pending_space,
    record_source_hash,
    space_readiness,
)
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

DIMENSIONS = VECTOR_COLUMN_DIMENSIONS
OLD, NEW = "identity-old", "identity-new"


class Embedder(DeterministicEmbeddingProvider):
    """A fake that counts what it was asked to send and can be told to fail."""

    def __init__(self, model_id, fail_on=(), deny_after=None):
        super().__init__(dimensions=DIMENSIONS, model_id=model_id)
        self.documents_sent = 0
        self.chunks_sent = 0
        self.lanes = []
        self._fail_on = set(fail_on)
        self._deny_after = deny_after
        self.hook = None
        self._inside_chunks = False

    def _attempt(self):
        self.lanes.append(lane_for("none"))
        if self._deny_after is not None and len(self.lanes) > self._deny_after:
            raise AdmissionDenied(CAMPAIGN_EXHAUSTED)

    def embed_documents(self, texts):
        # The base fake builds chunk vectors through this method; only a
        # direct call is a summary send.
        if not self._inside_chunks:
            self._attempt()
            self.documents_sent += len(texts)
        return super().embed_documents(texts)

    def embed_document_chunks(self, documents):
        self._attempt()
        if any(text in self._fail_on for doc in documents for text in doc):
            raise RuntimeError("the vendor fell over")
        if self.hook:
            self.hook()
        self.chunks_sent += sum(len(doc) for doc in documents)
        self._inside_chunks = True
        try:
            return super().embed_document_chunks(documents)
        finally:
            self._inside_chunks = False


@pytest.fixture
def active():
    EmbeddingSpace.objects.all().delete()
    return EmbeddingSpace.objects.create(
        model_id=OLD, dimensions=DIMENSIONS, metric="cosine",
        state=EmbeddingSpaceState.ACTIVE,
    )


@pytest.fixture
def pending(active):
    return EmbeddingSpace.objects.create(
        model_id=NEW, dimensions=DIMENSIONS, metric="cosine",
        state=EmbeddingSpaceState.PENDING,
    )


def _record(title="A thesis", chunks=("alpha", "beta"), abstract="An abstract."):
    record = Record.objects.create(
        title=title, abstract=abstract, is_ip=False,
        dpa_accepted_at=timezone.now(), embargo_answered_at=timezone.now(),
        pipeline_status=PipelineStatus.PUBLISHED,
    )
    if chunks:
        _chunk(record, *chunks)
    return record


def _chunk(record, *texts):
    values = tuple(
        Chunk(text=t, content=t, context_path=(), sequence=i, token_count=len(t.split()))
        for i, t in enumerate(texts)
    )
    DjangoChunkRepository().save(
        record_id=record.id, extraction_hash="x",
        chunk_set=ChunkSet(
            chunks=values, strategy_id="fixed-window", options=ChunkingOptions(),
            content_hash=chunkset_hash(values),
        ),
    )


def _index_active(record, active_space):
    """What the live path leaves behind for one record."""
    old = Embedder(OLD)
    embed_record_summary(record.id, provider=old)
    from apps.ai.indexing import embed_active_chunk_set
    embed_active_chunk_set(record.id, provider=old)


def _snapshot(space):
    return (
        sorted((r.record_id, r.source_hash, tuple(r.embedding))
               for r in RecordSpaceEmbedding.objects.filter(space=space)),
        sorted((c.chunk_id, tuple(c.embedding))
               for c in ChunkEmbedding.objects.filter(space=space)),
    )


class SpaceKeyedRecordVectorsTests:
    def test_the_live_summary_path_keeps_the_legacy_row_and_adds_a_space_keyed_one(self, active):
        record = _record()

        embed_record_summary(record.id, provider=Embedder(OLD))

        legacy = RecordEmbedding.objects.get(record=record)
        keyed = RecordSpaceEmbedding.objects.get(record=record, space=active)
        assert legacy.model_name == OLD
        assert list(keyed.embedding) == pytest.approx(list(legacy.embedding))
        assert keyed.source_hash == record_source_hash(record)

    def test_one_vector_per_record_per_space(self, active, pending):
        record = _record()
        RecordSpaceEmbedding.objects.create(
            record=record, space=active, embedding=[0.1] * DIMENSIONS, source_hash="a")
        RecordSpaceEmbedding.objects.create(
            record=record, space=pending, embedding=[0.2] * DIMENSIONS, source_hash="a")

        with pytest.raises(Exception):
            RecordSpaceEmbedding.objects.create(
                record=record, space=pending, embedding=[0.3] * DIMENSIONS, source_hash="b")


class BuildingAPendingSpaceTests:
    def test_a_build_fills_the_pending_space_and_touches_nothing_active(self, active, pending):
        record = _record()
        _index_active(record, active)
        before = _snapshot(active)
        legacy_before = list(RecordEmbedding.objects.values_list("record_id", "model_name"))
        legacy_vector = list(RecordEmbedding.objects.get(record=record).embedding)

        report = build_pending_space(pending.id, provider=Embedder(NEW))

        assert report.records_built == 1
        assert RecordSpaceEmbedding.objects.filter(space=pending, record=record).count() == 1
        assert ChunkEmbedding.objects.filter(space=pending).count() == 2
        assert _snapshot(active) == before
        assert list(RecordEmbedding.objects.values_list("record_id", "model_name")) == legacy_before
        assert list(RecordEmbedding.objects.get(record=record).embedding) == legacy_vector

    def test_the_new_identity_really_embeds_differently(self, active, pending):
        record = _record()
        _index_active(record, active)

        build_pending_space(pending.id, provider=Embedder(NEW))

        old = RecordSpaceEmbedding.objects.get(record=record, space=active)
        new = RecordSpaceEmbedding.objects.get(record=record, space=pending)
        assert list(old.embedding) != list(new.embedding)

    @pytest.mark.parametrize("state", [EmbeddingSpaceState.ACTIVE, EmbeddingSpaceState.RETIRED])
    def test_only_a_pending_space_can_be_built(self, active, pending, state):
        target = active
        if state == EmbeddingSpaceState.RETIRED:
            EmbeddingSpace.objects.filter(pk=pending.pk).update(state=state)
            target = pending
        _record()

        with pytest.raises(BuildRefused):
            build_pending_space(target.id, provider=Embedder(target.model_id))

        assert not RecordSpaceEmbedding.objects.exists()
        assert not ChunkEmbedding.objects.exists()

    def test_a_provider_that_is_not_the_pinned_identity_is_refused_before_any_send(self, active, pending):
        _record()
        wrong = Embedder("some-other-model")
        unknown = Embedder(None)

        for provider in (wrong, unknown):
            with pytest.raises(BuildRefused):
                build_pending_space(pending.id, provider=provider)

        assert wrong.documents_sent == wrong.chunks_sent == 0
        assert unknown.documents_sent == unknown.chunks_sent == 0

    def test_a_dimension_the_columns_cannot_hold_is_refused(self, active):
        wide = EmbeddingSpace.objects.create(
            model_id="wide", dimensions=2048, metric="cosine",
            state=EmbeddingSpaceState.PENDING)

        with pytest.raises(BuildRefused):
            build_pending_space(wide.id, provider=Embedder("wide"))

    def test_a_non_cosine_metric_is_refused(self, active):
        dot = EmbeddingSpace.objects.create(
            model_id=NEW, dimensions=DIMENSIONS, metric="dot",
            state=EmbeddingSpaceState.PENDING)

        with pytest.raises(BuildRefused):
            build_pending_space(dot.id, provider=Embedder(NEW))

    def test_nothing_in_a_build_can_activate_a_space(self, active, pending):
        _record()

        build_pending_space(pending.id, provider=Embedder(NEW))

        assert EmbeddingSpace.objects.get(pk=pending.pk).state == EmbeddingSpaceState.PENDING
        assert EmbeddingSpace.objects.get(pk=active.pk).state == EmbeddingSpaceState.ACTIVE


class ReadersStayOnTheActiveSpaceTests:
    def _scene(self, space, embedder):
        reader = make_user("reader@cit.edu")
        records = [
            make_record(title="Flood prediction", text="rainfall gauge flooding network",
                        embedder=embedder, space=space),
            make_record(title="Pond stocking", text="tilapia brackish water ponds",
                        embedder=embedder, space=space),
            make_record(title="Rainfall networks", text="rainfall catchment flooding model",
                        embedder=embedder, space=space),
        ]
        Record.objects.filter(pk__in=[r.pk for r in records]).update(
            is_ip=False, dpa_accepted_at=timezone.now(), embargo_answered_at=timezone.now())
        return reader, records

    def _read(self, reader, records, embedder):
        passages = TwoStageRetriever(embedder).retrieve("rainfall flooding", reader, limit=10)
        similar = similar_records(records[0], reader, limit=5)
        return (
            [(p.chunk_id, round(p.score, 9)) for p in passages.passages],
            [(m.record.pk, round(m.score, 9)) for m in similar],
            ChunkEmbedding.objects.filter(space=passages.embedding_space_id).count(),
        )

    def test_a_partial_pending_build_changes_no_search_count_or_similarity(self, active):
        reader_embedder = DeterministicEmbeddingProvider(dimensions=DIMENSIONS)
        active = EmbeddingSpace.objects.get(pk=active.pk)
        EmbeddingSpace.objects.filter(pk=active.pk).update(model_id="fake-test")
        active.refresh_from_db()
        reader, records = self._scene(active, reader_embedder)
        pending = EmbeddingSpace.objects.create(
            model_id=NEW, dimensions=DIMENSIONS, metric="cosine",
            state=EmbeddingSpaceState.PENDING)
        before = self._read(reader, records, reader_embedder)
        assert before[0], "the scene must return something for this to prove anything"

        report = build_pending_space(pending.id, provider=Embedder(NEW), max_records=1)

        assert report.stopped == "max_records"
        assert RecordSpaceEmbedding.objects.filter(space=pending).count() == 1
        assert ChunkEmbedding.objects.filter(space=pending).count() == 1
        assert self._read(reader, records, reader_embedder) == before

    def test_status_counts_only_the_active_space(self, active, client_for=None):
        from rest_framework.test import APIClient

        reader = make_user("status@cit.edu")
        embedder = DeterministicEmbeddingProvider(dimensions=DIMENSIONS)
        make_record(title="Flood", text="rainfall flooding", embedder=embedder, space=active)
        pending = EmbeddingSpace.objects.create(
            model_id=NEW, dimensions=DIMENSIONS, metric="cosine",
            state=EmbeddingSpaceState.PENDING)
        Record.objects.update(is_ip=False, dpa_accepted_at=timezone.now(),
                              embargo_answered_at=timezone.now())
        client = APIClient()
        client.force_authenticate(user=reader)

        before = client.get("/api/v1/ai/status/").json()
        build_pending_space(pending.id, provider=Embedder(NEW))

        assert client.get("/api/v1/ai/status/").json() == before

    def test_only_the_build_and_indexing_modules_name_the_space_keyed_table(self):
        """A reader of `RecordSpaceEmbedding` must name its space. Until IR-739
        moves the readers, the table has exactly these callers."""
        import ast
        from testing.source_files import python_sources

        apps_ai = pathlib.Path(__file__).resolve().parents[1]
        allowed = {"space_build.py", "indexing.py", "embedding.py", "__init__.py",
                   "backfill.py", "check_vector_index.py"}
        named = []
        for path in python_sources(apps_ai):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(isinstance(n, ast.Name) and n.id == "RecordSpaceEmbedding"
                   or isinstance(n, ast.alias) and n.name == "RecordSpaceEmbedding"
                   for n in ast.walk(tree)):
                named.append(path.name)
        assert set(named) <= allowed, named


class ABuildThatStopsAndRestartsTests:
    def test_a_bounded_build_resumes_and_a_finished_one_costs_nothing(self, active, pending):
        records = [_record(f"Paper {i}", chunks=(f"c{i}a", f"c{i}b")) for i in range(3)]
        first = Embedder(NEW)

        one = build_pending_space(pending.id, provider=first, max_records=2)

        assert one.records_built == 2 and one.stopped == "max_records"
        assert first.chunks_sent == 4

        second = Embedder(NEW)
        two = build_pending_space(pending.id, provider=second)
        assert two.records_built == 1 and two.stopped == ""
        assert second.chunks_sent == 2 and second.documents_sent == 1

        third = Embedder(NEW)
        three = build_pending_space(pending.id, provider=third)
        assert three.records_built == 0
        assert third.chunks_sent == third.documents_sent == 0
        assert RecordSpaceEmbedding.objects.filter(space=pending).count() == len(records)

    def test_a_token_budget_stops_before_the_record_that_would_exceed_it(self, active, pending):
        _record("One", chunks=("word " * 50,))
        _record("Two", chunks=("word " * 50,))

        report = build_pending_space(pending.id, provider=Embedder(NEW), token_budget=80)

        assert report.stopped == "token_budget"
        assert report.records_built == 1

    def test_a_failure_keeps_finished_work_and_only_the_failed_record_is_sent_again(self, active, pending):
        _record("Good one", chunks=("good",))
        _record("Bad one", chunks=("bad",))
        _record("Good two", chunks=("fine",))

        report = build_pending_space(pending.id, provider=Embedder(NEW, fail_on=("bad",)))

        assert [f[0] for f in report.failed] == [Record.objects.get(title="Bad one").pk]
        assert report.records_built == 2
        retry = Embedder(NEW)
        again = build_pending_space(pending.id, provider=retry)
        assert again.records_built == 1
        assert retry.chunks_sent == 1

    def test_a_redelivered_build_skips_a_record_another_worker_holds(self, active, pending):
        record = _record()
        settings_dict = connection.settings_dict
        import psycopg2

        other = psycopg2.connect(
            dbname=settings_dict["NAME"], user=settings_dict["USER"],
            password=settings_dict["PASSWORD"], host=settings_dict["HOST"],
            port=settings_dict["PORT"])
        other.autocommit = True
        try:
            from apps.ai.space_build import record_lock_keys
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(%s, %s)", record_lock_keys(pending.id, record.id))
            provider = Embedder(NEW)

            report = build_pending_space(pending.id, provider=provider)

            assert report.busy == [record.id]
            assert provider.chunks_sent == provider.documents_sent == 0
        finally:
            other.close()


class EveryAttemptIsCheckedTests:
    def test_embedding_is_charged_to_the_ingestion_lane(self, active, pending):
        _record()
        provider = Embedder(NEW)

        build_pending_space(pending.id, provider=provider)

        assert provider.lanes and set(provider.lanes) == {"ingestion"}

    def test_a_refused_admission_stops_the_run_and_keeps_what_finished(self, active, pending):
        _record("First", chunks=("a",))
        _record("Second", chunks=("b",))
        _record("Third", chunks=("c",))
        provider = Embedder(NEW, deny_after=2)

        report = build_pending_space(pending.id, provider=provider)

        assert report.stopped == f"admission:{CAMPAIGN_EXHAUSTED}"
        assert report.records_built == 1
        assert RecordSpaceEmbedding.objects.filter(space=pending).count() == 1
        assert len(provider.lanes) == 3, "no attempt is made after a sticky refusal"

    def test_a_record_the_gate_refuses_is_never_sent(self, active, pending):
        record = _record()
        Record.objects.filter(pk=record.pk).update(embargo_answered_at=None)
        provider = Embedder(NEW)

        report = build_pending_space(pending.id, provider=provider)

        assert [r[0] for r in report.refused] == [record.id]
        assert provider.documents_sent == provider.chunks_sent == 0
        assert not RecordSpaceEmbedding.objects.exists()

    def test_a_manuscript_replaced_during_the_send_does_not_publish_the_old_vectors(self, active, pending):
        record = _record(chunks=("old a", "old b"))
        provider = Embedder(NEW)
        provider.hook = lambda: _chunk(record, "new a", "new b", "new c")

        report = build_pending_space(pending.id, provider=provider)

        assert [r[0] for r in report.refused] == [record.id]
        old_ids = list(ChunkEmbedding.objects.filter(space=pending).values_list("chunk__text", flat=True))
        assert not any(text.startswith("old") for text in old_ids)

        healed = build_pending_space(pending.id, provider=Embedder(NEW))
        assert healed.records_built == 1
        assert sorted(ChunkEmbedding.objects.filter(space=pending)
                      .values_list("chunk__text", flat=True)) == ["new a", "new b", "new c"]

    def test_an_edited_abstract_re_embeds_only_that_summary(self, active, pending):
        edited = _record("Edited", chunks=("one",))
        _record("Untouched", chunks=("two",))
        build_pending_space(pending.id, provider=Embedder(NEW))
        old_hash = RecordSpaceEmbedding.objects.get(record=edited, space=pending).source_hash
        Record.objects.filter(pk=edited.pk).update(abstract="A different abstract.")

        provider = Embedder(NEW)
        build_pending_space(pending.id, provider=provider)

        assert provider.documents_sent == 1
        assert provider.chunks_sent == 0
        assert RecordSpaceEmbedding.objects.get(record=edited, space=pending).source_hash != old_hash


class ReadinessTests:
    def test_coverage_is_partial_until_every_record_and_chunk_is_built(self, active, pending):
        _record("One"), _record("Two")
        build_pending_space(pending.id, provider=Embedder(NEW), max_records=1)

        partial = space_readiness(pending.id)
        build_pending_space(pending.id, provider=Embedder(NEW))
        complete = space_readiness(pending.id)

        assert not partial.ready and partial.summaries_missing == 1 and partial.passages_missing == 2
        assert complete.ready and complete.summaries_missing == 0 and complete.passages_missing == 0
        assert complete.dimension_mismatches == 0

    def test_a_stale_summary_is_not_ready(self, active, pending):
        record = _record()
        build_pending_space(pending.id, provider=Embedder(NEW))
        Record.objects.filter(pk=record.pk).update(title="Renamed")

        readiness = space_readiness(pending.id)

        assert readiness.summaries_stale == 1 and not readiness.ready

    def test_the_promote_check_reports_summaries_and_activates_nothing(self, active, pending, capsys):
        _record()
        build_pending_space(pending.id, provider=Embedder(NEW), max_records=0)
        call_command("promote_embedding_space", "--space", str(pending.id), "--check")
        out = capsys.readouterr().out

        assert "summary" in out.lower() and "dimension" in out.lower()
        assert EmbeddingSpace.objects.get(pk=pending.pk).state == EmbeddingSpaceState.PENDING

    def test_the_vector_index_check_can_look_at_a_pending_space(self, active, pending, capsys):
        _record()
        build_pending_space(pending.id, provider=Embedder(NEW))

        call_command("check_vector_index", "--space", str(pending.id))

        assert f"space {pending.id}" in capsys.readouterr().out


class TheOperatorCommandTests:
    def test_backfill_into_a_pending_space_builds_summaries_too(self, active, pending, monkeypatch):
        record = _record()
        monkeypatch.setattr(
            "apps.ai.indexing.build_embedding_provider", lambda: Embedder(NEW))

        call_command("backfill_embeddings", "--space", str(pending.id))

        assert RecordSpaceEmbedding.objects.filter(record=record, space=pending).exists()
        assert not RecordEmbedding.objects.filter(model_name=NEW).exists()
