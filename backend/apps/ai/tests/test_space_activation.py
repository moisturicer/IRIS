"""Promoting a verified Embedding Space, and rolling back to the one before
(IR-739, ADR-049 §23, ADR-015).

Two deterministic embedding identities stand in for an old and a new model. The
old one is active and serves readers; the new one is built beside it (IR-752).
What is demonstrated, on a real PostgreSQL with no vendor:

* promotion refuses an incomplete, mis-shaped, stale or unhealthy space, naming
  every reason, and changes nothing when it does;
* a complete space goes live as a Record-and-Passage pair: the readers' summary
  stage and passage stage move together, and a reader whose query model is not
  the live space's finds nothing rather than something from the wrong space;
* the previous space is kept, rollback returns to it, and neither move can
  surface a source that has since been deleted, hidden or tombstoned;
* a rollback target that fell behind is refused until it is reopened and built.

The races and the failed-activation transaction run on independent connections
in ``test_space_activation_races_db.py``.
"""

import uuid

import pytest
from django.utils import timezone

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.indexing import embed_active_chunk_set, embed_record_summary
from apps.ai.models import (
    VECTOR_COLUMN_DIMENSIONS,
    EmbeddingSpace,
    EmbeddingSpaceActivation,
    EmbeddingSpaceState,
)
from apps.ai.models.chunk import ChunkEmbedding, DocumentChunk
from apps.ai.models.embedding import RecordSpaceEmbedding
from apps.ai.promotion import PromotionRefused, promote
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.repositories import DjangoChunkRepository
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.ai.space_activation import (
    ActivationRefused,
    activate_space,
    check_activation,
    reader_probe,
    reopen_rollback_target,
    rollback_target,
)
from apps.ai.space_build import build_pending_space
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record
from core.enums import PipelineStatus

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

DIMENSIONS = VECTOR_COLUMN_DIMENSIONS
OLD, NEW = "identity-old", "identity-new"


def embedder(model):
    return DeterministicEmbeddingProvider(dimensions=DIMENSIONS, model_id=model)


def factory(model):
    return embedder(model)


def record(title, chunks=("alpha", "beta"), abstract="An abstract.", released=True):
    # Every paper starts embargoed (IR-882); released, so only what a test asks holds it.
    stamps = {"is_embargoed": False, "embargo_released_at": timezone.now()} if released else {}
    rec = Record.objects.create(
        title=title, abstract=abstract, is_ip=False, ai_consent=True,
        pipeline_status=PipelineStatus.PUBLISHED, **stamps)
    values = tuple(
        Chunk(text=t, content=t, context_path=(), sequence=i, token_count=len(t.split()))
        for i, t in enumerate(chunks))
    DjangoChunkRepository().save(
        record_id=rec.id, extraction_hash="x",
        chunk_set=ChunkSet(chunks=values, strategy_id="fixed-window", options=ChunkingOptions(),
                           content_hash=chunkset_hash(values)))
    return rec


def index_active(rec):
    """What the live path leaves behind for one record, under the active space."""
    provider = embedder(OLD)
    embed_record_summary(rec.id, provider=provider)
    embed_active_chunk_set(rec.id, provider=provider)


def build(space, model):
    return build_pending_space(space.id, provider=embedder(model))


def codes(refusal):
    return {r.code for r in refusal.verdict.refusals}


def states():
    return {s.model_id: s.state for s in EmbeddingSpace.objects.all()}


def search(user, model, question="alpha", space=None):
    return TwoStageRetriever(embedder(model), space=space).retrieve(question, user, limit=20)


def cited_records(result):
    return {p.record_id for p in result.passages}


class RefusalTests:
    def test_an_incomplete_space_is_refused_with_every_reason_and_changes_nothing(self, active, pending):
        rec = record("Flood study")
        index_active(rec)

        with pytest.raises(ActivationRefused) as refused:
            activate_space(pending.id, provider_factory=factory, verify_index=False)

        assert {"summary_coverage", "passage_coverage"} <= codes(refused.value)
        assert "half-indexed" in str(refused.value)
        assert states() == {OLD: EmbeddingSpaceState.ACTIVE, NEW: EmbeddingSpaceState.PENDING}
        assert not EmbeddingSpaceActivation.objects.exists()

    def test_a_partly_built_space_is_refused(self, active, pending):
        for n in range(3):
            index_active(record(f"Paper {n}", chunks=(f"c{n}a", f"c{n}b")))
        build_pending_space(pending.id, provider=embedder(NEW), max_records=2)

        with pytest.raises(ActivationRefused) as refused:
            activate_space(pending.id, provider_factory=factory, verify_index=False)

        assert refused.value.verdict.checks["summaries_missing"] == 1
        assert refused.value.verdict.checks["passage_shortfall_records"] == 1

    def test_the_wrong_width_and_metric_are_refused(self, active):
        wrong = EmbeddingSpace.objects.create(
            model_id=NEW, dimensions=512, metric="dot", state=EmbeddingSpaceState.PENDING)

        with pytest.raises(PromotionRefused) as refused:
            promote(wrong)

        assert "512 dimensions" in str(refused.value)
        assert {"dimensions", "metric"} <= codes(refused.value)

    def test_a_stored_vector_of_the_wrong_width_is_refused(self, active, pending):
        from django.db import connection

        rec = record("Flood study")
        index_active(rec)
        build(pending, NEW)
        # The column is vector(1024); a narrower vector cannot be stored, so the
        # check is exercised through the space row, which claims a width that
        # its stored vectors do not have.
        EmbeddingSpace.objects.filter(pk=pending.pk).update(dimensions=512)
        pending.refresh_from_db()

        verdict = check_activation(pending, provider_factory=factory, verify_index=False)

        assert not verdict.ok
        assert verdict.checks["dimension_mismatches"] > 0
        assert "dimensions" in {r.code for r in verdict.refusals}
        assert connection.cursor()  # the connection is still usable

    def test_the_query_provider_must_name_the_spaces_model(self, active, pending):
        rec = record("Flood study")
        index_active(rec)
        build(pending, NEW)

        wrong_model = check_activation(
            pending, provider_factory=lambda model: embedder(OLD), verify_index=False)
        unnamed = check_activation(
            pending, provider_factory=lambda model: DeterministicEmbeddingProvider(dimensions=DIMENSIONS),
            verify_index=False)

        def explode(model):
            raise RuntimeError("no key")

        unbuildable = check_activation(pending, provider_factory=explode, verify_index=False)

        for verdict in (wrong_model, unnamed, unbuildable):
            assert "query_semantics" in {r.code for r in verdict.refusals}
        assert check_activation(pending, provider_factory=factory, verify_index=False).ok

    def test_a_summary_whose_text_changed_is_stale(self, active, pending):
        rec = record("Flood study", abstract="Original abstract.")
        index_active(rec)
        build(pending, NEW)
        Record.objects.filter(pk=rec.pk).update(abstract="A rewritten abstract.")

        verdict = check_activation(pending, provider_factory=factory, verify_index=False)

        assert verdict.checks["summaries_stale"] == 1
        assert "summary_coverage" in {r.code for r in verdict.refusals}

    def test_a_chunk_set_that_is_not_the_current_manuscript_revision_is_refused(self, active, pending):
        rec = record("Flood study")
        index_active(rec)
        build(pending, NEW)
        # The Record's current Manuscript moved on; the chunk set (and every
        # vector built on it) belongs to a revision that is no longer canonical.
        PdfExtraction.objects.create(
            record=rec, kind=DocumentKind.MANUSCRIPT, source_revision=uuid.uuid4(), status="done")
        rec.chunk_sets.update(source_revision=uuid.uuid4())

        verdict = check_activation(pending, provider_factory=factory, verify_index=False)

        assert verdict.checks["stale_revision_records"] == 1
        assert "stale_revision" in {r.code for r in verdict.refusals}

    def test_an_unverified_summary_blocks_a_promotion(self, active, pending):
        rec = record("Flood study")
        index_active(rec)
        build(pending, NEW)
        RecordSpaceEmbedding.objects.filter(space=pending, record=rec).update(source_hash="")

        verdict = check_activation(pending, provider_factory=factory, verify_index=False)

        assert verdict.checks["summaries_unverified"] == 1
        assert not verdict.ok

    def test_a_failed_retrieval_check_is_refused(self, active, pending, monkeypatch):
        from apps.ai import index_health

        rec = record("Flood study")
        index_active(rec)
        build(pending, NEW)
        real = index_health.measure_index_recall

        def degraded(model, **kwargs):
            result = real(model, **kwargs)
            return result._replace(recall=0.5) if hasattr(result, "_replace") else type(result)(
                **{**result.__dict__, "recall": 0.5})

        monkeypatch.setattr(index_health, "measure_index_recall", degraded)

        verdict = check_activation(pending, provider_factory=factory, verify_index=True)

        assert "retrieval_check" in {r.code for r in verdict.refusals}

    def test_a_healthy_small_index_passes_the_retrieval_check(self, active, pending):
        rec = record("Flood study")
        index_active(rec)
        build(pending, NEW)

        verdict = check_activation(pending, provider_factory=factory, verify_index=True)

        assert verdict.ok, verdict.message()
        assert verdict.checks["chunk_index_recall"] >= 0.99

    def test_records_no_reader_can_use_are_not_owed_a_vector(self, active, pending):
        kept = record("Kept")
        index_active(kept)
        gated = record("Never released", released=False)
        deleted = record("Deleted")
        Record.objects.filter(pk=deleted.pk).update(is_deleted=True)
        build(pending, NEW)

        verdict = check_activation(pending, provider_factory=factory, verify_index=False)

        assert verdict.ok, verdict.message()
        assert verdict.checks["records_owed"] == 1
        assert not RecordSpaceEmbedding.objects.filter(space=pending, record=gated).exists()

    def test_a_retired_space_cannot_be_promoted(self, active, pending):
        activate_space(pending.id, provider_factory=factory, verify_index=False)
        retired = EmbeddingSpace.objects.get(pk=active.pk)

        with pytest.raises(ActivationRefused) as refused:
            activate_space(retired.id, provider_factory=factory, verify_index=False)

        assert "retired" in codes(refused.value)

    def test_the_active_space_is_not_promoted_again(self, active):
        with pytest.raises(ActivationRefused) as refused:
            activate_space(active.id, provider_factory=factory, verify_index=False)

        assert "already_active" in codes(refused.value)


class PromotionTests:
    def _two_papers(self):
        papers = [record("Flood prediction", chunks=("rainfall flooding network",)),
                  record("Pond stocking", chunks=("tilapia brackish ponds",))]
        for paper in papers:
            index_active(paper)
        return papers

    def test_a_complete_pair_goes_live_and_the_old_space_is_kept(self, active, pending, reader):
        self._two_papers()
        build(pending, NEW)

        result = activate_space(
            pending.id, provider_factory=factory, actor="op@cit.edu", verify_index=False)

        assert result.activated and result.previous_space_id == active.pk
        assert states() == {OLD: EmbeddingSpaceState.RETIRED, NEW: EmbeddingSpaceState.ACTIVE}
        row = EmbeddingSpaceActivation.objects.get()
        assert (row.kind, row.space_id, row.previous_space_id, row.actor) == (
            "promote", pending.pk, active.pk, "op@cit.edu")
        assert row.report["records_owed"] == 2
        assert ChunkEmbedding.objects.filter(space=active).exists(), "kept, not deleted"
        assert RecordSpaceEmbedding.objects.filter(space=active).count() == 2

    def test_readers_move_as_a_pair_and_never_mix_spaces(self, active, pending, reader):
        self._two_papers()
        build(pending, NEW)
        before = search(reader, OLD, "rainfall flooding")
        assert before.embedding_space_id == active.pk and before.passages

        activate_space(pending.id, provider_factory=factory)

        after = search(reader, NEW, "rainfall flooding")
        assert after.embedding_space_id == pending.pk and after.passages
        # Every passage the reader was handed carries a vector of the NEW space,
        # and its Record was found through the NEW space's summary vector.
        for passage in after.passages:
            assert ChunkEmbedding.objects.filter(chunk_id=passage.chunk_id, space=pending).exists()
            assert RecordSpaceEmbedding.objects.filter(record_id=passage.record_id, space=pending).exists()
        # A query embedded by the old model against the new space is a vector in
        # the wrong space: it finds nothing instead of something plausible.
        stale_reader = search(reader, OLD, "rainfall flooding")
        assert stale_reader.passages == ()

    def test_a_dry_run_reports_the_verdict_and_changes_nothing(self, active, pending):
        self._two_papers()
        build(pending, NEW)

        result = activate_space(pending.id, provider_factory=factory, dry_run=True)

        assert result.dry_run and not result.activated and result.verdict.ok
        assert states() == {OLD: EmbeddingSpaceState.ACTIVE, NEW: EmbeddingSpaceState.PENDING}
        assert not EmbeddingSpaceActivation.objects.exists()

    def test_a_dry_run_of_an_incomplete_space_reports_instead_of_raising(self, active, pending):
        self._two_papers()

        result = activate_space(pending.id, provider_factory=factory, dry_run=True)

        assert not result.verdict.ok and not result.activated
        assert result.as_dict()["verdict"]["refusals"]

    def test_a_move_checked_against_another_active_space_is_refused(self, active, pending):
        self._two_papers()
        build(pending, NEW)

        with pytest.raises(ActivationRefused) as refused:
            activate_space(pending.id, provider_factory=factory, expect_active=active.pk + 999)

        assert "active_changed" in codes(refused.value)
        assert states()[NEW] == EmbeddingSpaceState.PENDING

    def test_the_first_space_can_be_activated_when_none_is_live(self):
        EmbeddingSpace.objects.all().delete()
        first = EmbeddingSpace.objects.create(
            model_id=NEW, dimensions=DIMENSIONS, metric="cosine", state=EmbeddingSpaceState.PENDING)

        result = activate_space(first.id, provider_factory=factory, verify_index=False)

        assert result.activated and result.previous_space_id is None
        assert EmbeddingSpaceActivation.objects.get().previous_space_id is None
        assert rollback_target() is None


class RollbackTests:
    def _promoted(self, reader):
        papers = [record("Flood prediction", chunks=("rainfall flooding network",)),
                  record("Pond stocking", chunks=("tilapia brackish ponds",))]
        for paper in papers:
            index_active(paper)
        return papers

    def test_rollback_returns_to_the_previous_revision_and_readers_follow(self, active, pending, reader):
        self._promoted(reader)
        build(pending, NEW)
        activate_space(pending.id, provider_factory=factory)
        assert rollback_target().pk == active.pk

        result = activate_space(active.id, kind="rollback", provider_factory=factory, actor="op@cit.edu")

        assert result.activated
        assert states() == {OLD: EmbeddingSpaceState.ACTIVE, NEW: EmbeddingSpaceState.RETIRED}
        last = EmbeddingSpaceActivation.objects.first()
        assert (last.kind, last.space_id, last.previous_space_id) == ("rollback", active.pk, pending.pk)
        back = search(reader, OLD, "rainfall flooding")
        assert back.embedding_space_id == active.pk and back.passages
        assert search(reader, NEW, "rainfall flooding").passages == ()

    def test_only_the_replaced_space_is_a_rollback_target(self, active, pending):
        other = EmbeddingSpace.objects.create(
            model_id="third", dimensions=DIMENSIONS, metric="cosine", state=EmbeddingSpaceState.RETIRED)
        with pytest.raises(PromotionRefused, match="not the previous revision"):
            activate_space(other.id, kind="rollback", provider_factory=factory)

        index_active(record("Flood"))
        build(pending, NEW)
        activate_space(pending.id, provider_factory=factory, verify_index=False)
        with pytest.raises(PromotionRefused, match="not the previous revision"):
            activate_space(other.id, kind="rollback", provider_factory=factory)

    def test_there_is_nothing_to_roll_back_to_before_any_promotion(self, active):
        assert rollback_target() is None
        with pytest.raises(PromotionRefused):
            activate_space(active.id, kind="rollback", provider_factory=factory)

    def test_a_target_that_fell_behind_is_refused_until_reopened_and_rebuilt(self, active, pending, reader):
        self._promoted(reader)
        build(pending, NEW)
        activate_space(pending.id, provider_factory=factory, verify_index=False)
        # Indexed after the promotion, so only the live (NEW) space holds it.
        late = record("Late paper", chunks=("late finding",))
        newer = embedder(NEW)
        embed_record_summary(late.id, provider=newer)
        embed_active_chunk_set(late.id, provider=newer)

        with pytest.raises(ActivationRefused) as refused:
            activate_space(active.id, kind="rollback", provider_factory=factory, verify_index=False)
        assert {"summary_coverage", "passage_coverage"} <= codes(refused.value)
        assert states()[OLD] == EmbeddingSpaceState.RETIRED

        reopened = reopen_rollback_target()
        assert reopened.state == EmbeddingSpaceState.PENDING
        build(reopened, OLD)
        result = activate_space(active.id, kind="rollback", provider_factory=factory, verify_index=False)
        assert result.activated
        assert search(reader, OLD, "late finding").embedding_space_id == active.pk

    def test_only_a_retired_rollback_target_can_be_reopened(self, active, pending):
        with pytest.raises(PromotionRefused):
            reopen_rollback_target()
        index_active(record("Flood"))
        build(pending, NEW)
        activate_space(pending.id, provider_factory=factory, verify_index=False)
        reopen_rollback_target()
        with pytest.raises(PromotionRefused, match="only a retired"):
            reopen_rollback_target()


class RevokedSourcesStayRevokedTests:
    """Rollback restores vectors, not access: every reader still applies the
    visibility predicate, the active chunk set and tombstones to what it returns."""

    def _scene(self, reader):
        keep = record("Kept paper", chunks=("rainfall flooding network",))
        target = record("Revoked paper", chunks=("rainfall flooding catchment",))
        for paper in (keep, target):
            index_active(paper)
        return keep, target

    def _promote_then_revoke_then_roll_back(self, pending, active, revoke):
        build(pending, NEW)
        activate_space(pending.id, provider_factory=factory, verify_index=False)
        revoke()
        return activate_space(active.id, kind="rollback", provider_factory=factory, verify_index=False)

    @pytest.mark.parametrize("how", ["deleted", "withdrawn", "tombstoned"])
    def test_a_source_revoked_after_the_promotion_is_not_resurrected(self, active, pending, reader, how):
        keep, target = self._scene(reader)

        def revoke():
            if how == "deleted":
                Record.objects.filter(pk=target.pk).update(is_deleted=True)
            elif how == "withdrawn":
                Record.objects.filter(pk=target.pk).update(pipeline_status=PipelineStatus.DRAFT)
            else:
                DocumentChunk.objects.filter(record=target).update(deleted_at=timezone.now())

        assert target.pk in cited_records(search(reader, OLD, "rainfall flooding"))

        result = self._promote_then_revoke_then_roll_back(pending, active, revoke)

        assert result.activated, "a revoked source is not owed a vector, so it cannot block"
        # The old space still holds the revoked source's vectors ...
        assert RecordSpaceEmbedding.objects.filter(space=active, record=target).exists()
        # ... and no reader can reach them.
        served = search(reader, OLD, "rainfall flooding")
        assert served.embedding_space_id == active.pk
        assert target.pk not in cited_records(served)
        if how == "tombstoned":
            assert keep.pk in cited_records(served)
        probe = reader_probe(active, reader)
        assert probe["ok"], probe["failures"]

    def test_a_manuscript_replaced_after_the_promotion_is_not_served_from_the_old_chunks(
        self, active, pending, reader,
    ):
        _, target = self._scene(reader)
        build(pending, NEW)
        activate_space(pending.id, provider_factory=factory, verify_index=False)
        # A new manuscript becomes the active chunk set; its vectors exist only
        # in the live (NEW) space.
        new_values = (Chunk(text="rewritten", content="rewritten", context_path=(), sequence=0, token_count=1),)
        DjangoChunkRepository().save(
            record_id=target.id, extraction_hash="y",
            chunk_set=ChunkSet(chunks=new_values, strategy_id="fixed-window", options=ChunkingOptions(),
                               content_hash=chunkset_hash(new_values)))

        with pytest.raises(ActivationRefused) as refused:
            activate_space(active.id, kind="rollback", provider_factory=factory, verify_index=False)

        assert "passage_coverage" in codes(refused.value)
        # The old chunk set is inactive, so even the live space cannot return it.
        old_ids = set(DocumentChunk.objects.filter(record=target, chunk_set__is_active=False).values_list("id", flat=True))
        served = search(reader, NEW, "alpha rainfall")
        assert not ({p.chunk_id for p in served.passages} & old_ids)


class ReaderProbeTests:
    def test_search_and_citations_hold_before_and_after_promotion_and_rollback(self, active, pending, reader):
        papers = [record("Flood prediction", chunks=("rainfall flooding network",)),
                  record("Pond stocking", chunks=("tilapia brackish ponds",))]
        for paper in papers:
            index_active(paper)
        build(pending, NEW)

        before = reader_probe(active, reader)
        pending_probe = reader_probe(pending, reader)
        activate_space(pending.id, provider_factory=factory, verify_index=False)
        after = reader_probe(pending, reader)
        activate_space(active.id, kind="rollback", provider_factory=factory, verify_index=False)
        restored = reader_probe(active, reader)

        for probe in (before, pending_probe, after, restored):
            assert probe["ok"], probe["failures"]
            assert probe["probes"] >= 2 and probe["passages_returned"] >= 2
            assert probe["own_chunk_found"] >= 1

    def test_the_probe_does_not_cite_what_the_reader_cannot_read(self, active, reader):
        hidden = record("Hidden draft", chunks=("secret finding",))
        Record.objects.filter(pk=hidden.pk).update(pipeline_status=PipelineStatus.DRAFT)
        index_active(hidden)

        probe = reader_probe(active, reader)

        assert probe["probes"] == 0 and probe["passages_returned"] == 0


class OperatorCommandTests:
    """The surface an operator uses: check, dry-run, result, probe, rollback."""

    @pytest.fixture(autouse=True)
    def _provider(self, monkeypatch):
        monkeypatch.setattr(
            "apps.ai.indexing.build_embedding_provider",
            lambda model=None: embedder(model or OLD))

    def _run(self, *args):
        import io
        import json

        from django.core.management import call_command

        out = io.StringIO()
        call_command("promote_embedding_space", *args, stdout=out)
        text = out.getvalue()
        return json.loads(text) if "--json" in args else text

    def _ready(self, pending):
        for n in range(2):
            index_active(record(f"Paper {n}", chunks=(f"c{n}a rainfall", f"c{n}b flooding")))
        build(pending, NEW)

    def test_check_reports_every_reason_and_changes_nothing(self, active, pending):
        index_active(record("Flood study"))

        text = self._run("--space", str(pending.id), "--check", "--skip-index-check")

        assert "would be refused" in text and "[summary_coverage]" in text
        assert states()[NEW] == EmbeddingSpaceState.PENDING

    def test_dry_run_exits_non_zero_when_refused_and_zero_when_ready(self, active, pending):
        from django.core.management import CommandError

        self._ready(pending)
        ready = self._run("--space", str(pending.id), "--dry-run", "--skip-index-check")
        assert "ready to go live" in ready
        assert states()[NEW] == EmbeddingSpaceState.PENDING
        RecordSpaceEmbedding.objects.filter(space=pending).first().delete()

        with pytest.raises(CommandError, match="Would be refused"):
            self._run("--space", str(pending.id), "--dry-run", "--skip-index-check")

    def test_promote_then_rollback_with_a_reader_probe_before_and_after(self, active, pending, reader):
        self._ready(pending)

        promoted = self._run(
            "--space", str(pending.id), "--probe-user", reader.email, "--actor", "op@cit.edu")
        assert "reader probe before" in promoted and "reader probe after" in promoted
        assert "0 problem(s)" in promoted and "Promoted space" in promoted
        assert states() == {OLD: EmbeddingSpaceState.RETIRED, NEW: EmbeddingSpaceState.ACTIVE}

        restored = self._run("--rollback", "--probe-user", reader.email)
        assert "Rolled back to space" in restored and "reader probe after" in restored
        assert states() == {OLD: EmbeddingSpaceState.ACTIVE, NEW: EmbeddingSpaceState.RETIRED}
        assert [a.kind for a in EmbeddingSpaceActivation.objects.order_by("id")] == ["promote", "rollback"]

    def test_the_result_is_available_as_json(self, active, pending):
        self._ready(pending)

        dry = self._run("--space", str(pending.id), "--dry-run", "--skip-index-check", "--json")
        done = self._run("--space", str(pending.id), "--skip-index-check", "--json")

        assert dry["dry_run"] is True and dry["verdict"]["ok"] is True
        assert done["activated"] is True and done["previous_space_id"] == active.pk
        assert done["verdict"]["checks"]["records_owed"] == 2

    def test_an_incomplete_promotion_is_refused_naming_the_short_records(self, active, pending):
        from django.core.management import CommandError

        paper = record("Flood study")
        index_active(paper)

        with pytest.raises(CommandError, match="half-indexed"):
            self._run("--space", str(pending.id), "--skip-index-check")

        assert states()[NEW] == EmbeddingSpaceState.PENDING

    def test_rollback_needs_a_recorded_previous_revision(self, active):
        from django.core.management import CommandError

        with pytest.raises(CommandError, match="no previous revision"):
            self._run("--rollback")

    def test_reopening_the_rollback_target_is_a_deliberate_command(self, active, pending):
        self._ready(pending)
        self._run("--space", str(pending.id), "--skip-index-check")

        text = self._run("--reopen-rollback-target")

        assert "pending again" in text
        assert states()[OLD] == EmbeddingSpaceState.PENDING
