"""Promotion races and a failed activation, on independent PostgreSQL connections
(IR-739, ADR-049 §23).

Every test commits its fixtures (``transaction=True``) and then runs the parties
on separate threads, each of which owns its own database connection, so the
locks, the visibility of committed rows and the rollback of an aborted
transaction are PostgreSQL's, not an in-memory stand-in:

* a reader in flight while a promotion commits stays on the space it resolved;
* two operators promoting different spaces cannot both land;
* a writer that holds a space makes the promotion wait, and what the writer
  commits is counted by the promotion's final check;
* a writer that began against the then-active space writes nothing to it once
  it is retired;
* a promotion that cannot get the lock refuses and changes nothing;
* a transaction that fails after retiring the old space leaves the old space
  active and unchanged, and no history row.
"""

import threading

import pytest
from django.db import DatabaseError, connections, transaction
from django.core.exceptions import ImproperlyConfigured

from apps.ai import indexing, space_activation
from apps.ai.indexing import embed_record_summary
from apps.ai.models import (
    EmbeddingSpace,
    EmbeddingSpaceActivation,
    EmbeddingSpaceState,
    get_active_embedding_space,
)
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.models.embedding import RecordSpaceEmbedding
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.ai.space_activation import ActivationRefused, activate_space

from .test_space_activation import (  # builders shared with the unit suite
    NEW,
    OLD,
    build,
    codes,
    embedder,
    factory,
    index_active,
    record,
    search,
    states,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

WAIT = 20


class Run(threading.Thread):
    """Run ``fn`` on its own connection; keep its result or its exception."""

    def __init__(self, fn):
        super().__init__(daemon=True)
        self._fn, self.result, self.error = fn, None, None

    def run(self):
        try:
            self.result = self._fn()
        except BaseException as exc:  # noqa: BLE001 - handed back to the test
            self.error = exc
        finally:
            connections.close_all()


def start(fn):
    thread = Run(fn)
    thread.start()
    return thread


def finish(thread):
    thread.join(WAIT)
    assert not thread.is_alive(), "the thread did not finish"
    return thread


def two_papers():
    papers = [record("Flood prediction", chunks=("rainfall flooding network",)),
              record("Pond stocking", chunks=("tilapia brackish ponds",))]
    for paper in papers:
        index_active(paper)
    return papers


def promote_now(space, **kwargs):
    return activate_space(space.id, provider_factory=factory, verify_index=False, **kwargs)


class HoldsASpace:
    """A writer: share-locks a space row in an open transaction until released."""

    def __init__(self, space, *, also=None):
        self.locked, self.release, self.done = threading.Event(), threading.Event(), threading.Event()
        self._space, self._also = space, also
        self.thread = start(self._run)

    def _run(self):
        try:
            with transaction.atomic():
                assert indexing._hold_space(self._space)
                if self._also:
                    self._also()
                self.locked.set()
                assert self.release.wait(WAIT)
        finally:
            self.locked.set()
            self.done.set()


class ReaderRaceTests:
    def test_a_reader_in_flight_stays_on_one_space_while_a_promotion_commits(self, active, pending, reader):
        two_papers()
        build(pending, NEW)

        class PromotesWhileQuerying(type(embedder(OLD))):
            def embed_query(self_inner, text):  # noqa: N805
                # The reader has already resolved the active space; the promotion
                # commits on another connection before it reads a single row.
                finish(start(lambda: promote_now(pending)))
                return super().embed_query(text)

        racing = PromotesWhileQuerying(dimensions=embedder(OLD).dimensions, model_id=OLD)
        result = TwoStageRetriever(racing).retrieve("rainfall flooding", reader, limit=20)

        assert states() == {OLD: EmbeddingSpaceState.RETIRED, NEW: EmbeddingSpaceState.ACTIVE}
        assert result.embedding_space_id == active.pk and result.passages
        for passage in result.passages:
            assert ChunkEmbedding.objects.filter(chunk_id=passage.chunk_id, space=active).exists()
            assert RecordSpaceEmbedding.objects.filter(record_id=passage.record_id, space=active).exists()
        # The next request starts after the flip and uses the new pair only.
        after = search(reader, NEW, "rainfall flooding")
        assert after.embedding_space_id == pending.pk and after.passages


class PromotionRaceTests:
    def test_two_operators_promoting_different_spaces_cannot_both_land(self, active, pending, reader):
        two_papers()
        other = EmbeddingSpace.objects.create(
            model_id="identity-third", dimensions=pending.dimensions, metric="cosine",
            state=EmbeddingSpaceState.PENDING)
        build(pending, NEW)
        build(other, "identity-third")
        gate = threading.Barrier(2)

        def promoting(space):
            def run():
                gate.wait(WAIT)
                return activate_space(
                    space.id, provider_factory=factory, verify_index=False, expect_active=active.pk)
            return run

        first, second = start(promoting(pending)), start(promoting(other))
        finish(first), finish(second)

        outcomes = [t for t in (first, second)]
        landed = [t for t in outcomes if t.error is None and t.result.activated]
        refused = [t for t in outcomes if isinstance(t.error, ActivationRefused)]
        assert len(landed) == 1 and len(refused) == 1, [t.error for t in outcomes]
        assert "active_changed" in codes(refused[0].error)
        assert EmbeddingSpace.objects.filter(state=EmbeddingSpaceState.ACTIVE).count() == 1
        assert EmbeddingSpaceActivation.objects.count() == 1
        winner = EmbeddingSpace.objects.get(state=EmbeddingSpaceState.ACTIVE)
        assert EmbeddingSpaceActivation.objects.get().space_id == winner.pk
        assert EmbeddingSpace.objects.get(pk=active.pk).state == EmbeddingSpaceState.RETIRED

    def test_a_writer_in_flight_makes_the_promotion_wait_and_its_commit_is_counted(
        self, active, pending, reader,
    ):
        two_papers()
        build(pending, NEW)
        late = {}

        def a_paper_indexed_under_the_old_space():
            late["record"] = record("Late paper", chunks=("late finding",))
            index_active(late["record"])

        writer = HoldsASpace(active, also=a_paper_indexed_under_the_old_space)
        assert writer.locked.wait(WAIT)

        promotion = start(lambda: promote_now(pending))
        assert not promotion.join(1.0) and promotion.is_alive(), "it must wait for the writer"
        assert states()[NEW] == EmbeddingSpaceState.PENDING

        writer.release.set()
        finish(writer.thread), finish(promotion)

        # The writer's paper exists only in the old space, so the promotion's
        # final check inside the lock refused it, and nothing moved.
        assert isinstance(promotion.error, ActivationRefused), promotion.error
        assert {"summary_coverage", "passage_coverage"} <= codes(promotion.error)
        assert states() == {OLD: EmbeddingSpaceState.ACTIVE, NEW: EmbeddingSpaceState.PENDING}
        assert not EmbeddingSpaceActivation.objects.exists()
        assert RecordSpaceEmbedding.objects.filter(space=active, record=late["record"]).exists()

    def test_a_promotion_that_cannot_get_the_lock_refuses_and_changes_nothing(self, active, pending):
        two_papers()
        build(pending, NEW)
        writer = HoldsASpace(active)
        assert writer.locked.wait(WAIT)

        try:
            with pytest.raises(ActivationRefused) as refused:
                promote_now(pending, lock_timeout_ms=300)
        finally:
            writer.release.set()
            finish(writer.thread)

        assert "busy" in codes(refused.value)
        assert states() == {OLD: EmbeddingSpaceState.ACTIVE, NEW: EmbeddingSpaceState.PENDING}
        assert not EmbeddingSpaceActivation.objects.exists()

    def test_a_writer_that_began_before_the_flip_writes_nothing_to_the_retired_space(
        self, active, pending, reader,
    ):
        two_papers()
        late = record("Late paper", chunks=("late finding",))
        build(pending, NEW)  # complete, including the paper the writer is about to index
        promotions = []

        class PromotesWhileEmbedding(type(embedder(OLD))):
            def embed_documents(self_inner, texts):  # noqa: N805
                # The vector is computed for the old space; the flip commits
                # before the writer's transaction takes its lock.
                promotions.append(finish(start(lambda: promote_now(pending))))
                return super().embed_documents(texts)

        writer = PromotesWhileEmbedding(dimensions=embedder(OLD).dimensions, model_id=OLD)

        outcome = embed_record_summary(late.id, provider=writer)

        assert promotions and promotions[0].error is None, promotions[0].error
        assert outcome.refused and "retired" in outcome.reason
        assert states()[OLD] == EmbeddingSpaceState.RETIRED
        assert not RecordSpaceEmbedding.objects.filter(space=active, record=late).exists()

    def test_a_worker_still_on_the_old_model_cannot_write_into_the_new_space(self, active, pending):
        two_papers()
        build(pending, NEW)
        promote_now(pending)
        late = record("Late paper", chunks=("late finding",))

        with pytest.raises(ImproperlyConfigured, match="vectors do not belong"):
            embed_record_summary(late.id, provider=embedder(OLD))

        assert not RecordSpaceEmbedding.objects.filter(record=late).exists()


class FailedActivationTests:
    def _assert_the_old_space_is_intact(self, active, pending, reader, before_vectors):
        assert states() == {OLD: EmbeddingSpaceState.ACTIVE, NEW: EmbeddingSpaceState.PENDING}
        assert get_active_embedding_space().pk == active.pk
        assert not EmbeddingSpaceActivation.objects.exists()
        assert RecordSpaceEmbedding.objects.filter(space=active).count() == before_vectors
        served = search(reader, OLD, "rainfall flooding")
        assert served.embedding_space_id == active.pk and served.passages

    def test_a_failure_writing_the_history_rolls_back_both_state_changes(
        self, active, pending, reader, monkeypatch,
    ):
        two_papers()
        build(pending, NEW)
        before = RecordSpaceEmbedding.objects.filter(space=active).count()

        def broken(*args, **kwargs):
            raise RuntimeError("disk full while recording the activation")

        monkeypatch.setattr(space_activation, "_record_activation", broken)

        with pytest.raises(RuntimeError, match="disk full"):
            promote_now(pending)

        self._assert_the_old_space_is_intact(active, pending, reader, before)

    def test_a_real_database_error_after_the_old_space_was_retired_is_rolled_back(
        self, active, pending, reader, monkeypatch,
    ):
        two_papers()
        build(pending, NEW)
        before = RecordSpaceEmbedding.objects.filter(space=active).count()
        real = space_activation._record_activation

        def too_wide(kind, *args, **kwargs):
            # `kind` is varchar(10): PostgreSQL itself rejects the row.
            return real("x" * 50, *args, **kwargs)

        monkeypatch.setattr(space_activation, "_record_activation", too_wide)

        with pytest.raises(DatabaseError):
            promote_now(pending)

        self._assert_the_old_space_is_intact(active, pending, reader, before)

    def test_a_failure_between_retiring_and_activating_leaves_the_old_space_active(
        self, active, pending, reader, monkeypatch,
    ):
        """The partial state: the old space already retired, the new one not yet
        active. The transaction must take the retirement back with it."""
        from django.db.models.query import QuerySet

        two_papers()
        build(pending, NEW)
        before = RecordSpaceEmbedding.objects.filter(space=active).count()
        real_update = QuerySet.update
        seen = []

        def update(queryset, **kwargs):
            if queryset.model is EmbeddingSpace and kwargs.get("state"):
                seen.append(kwargs["state"])
                if kwargs["state"] == EmbeddingSpaceState.ACTIVE:
                    # The retirement above has run inside this transaction.
                    assert EmbeddingSpace.objects.get(pk=active.pk).state == EmbeddingSpaceState.RETIRED
                    raise DatabaseError("the connection dropped")
            return real_update(queryset, **kwargs)

        monkeypatch.setattr(QuerySet, "update", update)

        with pytest.raises(DatabaseError, match="dropped"):
            promote_now(pending)
        monkeypatch.undo()

        assert seen == [EmbeddingSpaceState.RETIRED, EmbeddingSpaceState.ACTIVE]
        self._assert_the_old_space_is_intact(active, pending, reader, before)

    def test_a_refused_promotion_after_the_lock_changes_nothing(self, active, pending, reader):
        two_papers()
        build(pending, NEW)
        before = RecordSpaceEmbedding.objects.filter(space=active).count()

        with pytest.raises(ActivationRefused):
            promote_now(pending, expect_active=active.pk + 999)

        self._assert_the_old_space_is_intact(active, pending, reader, before)
