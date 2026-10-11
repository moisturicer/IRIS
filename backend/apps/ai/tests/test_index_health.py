"""Does the vector index return the neighbours an exact scan would (IR-442)?

The question this answers came from a real miss: a question naming a paper
almost word for word was answered "the sources do not contain this", because
the approximate index scan never reached that paper's passages. Nothing
noticed, because a retrieval miss reads as a fluent, plausible refusal.

The recall arithmetic and the title probe are pure and tested without a
database or a vendor. `measure_index_recall` needs real pgvector, so it
carries `db_required` and skips cleanly where there is none.
"""

import pytest
from django.db import connection
from django.utils import timezone

from apps.ai.chunking import Chunk, ChunkingOptions, ChunkSet, chunkset_hash
from apps.ai.index_health import (
    DEFAULT_MIN_RECALL,
    IndexRecall,
    TitleMiss,
    measure_index_recall,
    overview_question,
    probe_titles,
    recall_at_k,
)
from apps.ai.models import VECTOR_COLUMN_DIMENSIONS, EmbeddingSpace, EmbeddingSpaceState
from apps.ai.models.chunk import ChunkEmbedding
from apps.ai.repositories import DjangoChunkRepository
from apps.records.models import Record


class RecallArithmeticTests:
    """Recall is set overlap, not rank agreement: an approximate scan that
    returns the right ten in a different order has lost nothing."""

    def test_the_same_neighbours_are_perfect_recall(self):
        assert recall_at_k([1, 2, 3], [1, 2, 3]) == 1.0

    def test_a_different_order_is_still_perfect_recall(self):
        assert recall_at_k([1, 2, 3], [3, 1, 2]) == 1.0

    def test_no_shared_neighbours_is_zero(self):
        assert recall_at_k([1, 2, 3], [4, 5, 6]) == 0.0

    def test_half_the_neighbours_is_half(self):
        assert recall_at_k([1, 2, 3, 4], [1, 2, 9, 9]) == 0.5

    def test_an_exact_scan_with_no_neighbours_cannot_be_missed(self):
        """Nothing to find, so nothing was lost — and no division by zero."""
        assert recall_at_k([], []) == 1.0
        assert recall_at_k([], [1, 2]) == 1.0

    def test_a_short_approximate_result_loses_recall(self):
        """The failure this exists to catch: the scan stops early and returns
        fewer rows than asked for."""
        assert recall_at_k([1, 2, 3, 4], [1]) == 0.25


class OverviewQuestionTests:
    """The probe asks what a reader asks. Pinned because the measurement is
    only meaningful if the question is the one that failed."""

    def test_it_wraps_the_title_the_way_a_reader_would(self):
        assert overview_question("A Thesis") == (
            "Can you give me the overview of A Thesis"
        )


class _FakeRetrieve:
    """Stands in for the retrieval stack: question in, record ids out."""

    def __init__(self, results):
        self._results = results
        self.asked = []

    def __call__(self, question, limit):
        self.asked.append((question, limit))
        return self._results.get(question, ())


class TitleProbeTests:
    def test_a_record_that_retrieves_itself_is_not_a_miss(self):
        retrieve = _FakeRetrieve({overview_question("A Thesis"): (7, 8)})

        misses = probe_titles([(7, "A Thesis")], retrieve, limit=10)

        assert misses == ()

    def test_a_record_absent_from_its_own_results_is_reported(self):
        retrieve = _FakeRetrieve({overview_question("A Thesis"): (8, 9)})

        misses = probe_titles([(7, "A Thesis")], retrieve, limit=10)

        assert misses == (TitleMiss(record_id=7, title="A Thesis", returned=(8, 9)),)

    def test_it_reports_what_came_back_instead(self):
        """Naming the record that won is what made the original miss
        diagnosable at all."""
        retrieve = _FakeRetrieve({overview_question("A Thesis"): (92, 92)})

        (miss,) = probe_titles([(7, "A Thesis")], retrieve, limit=10)

        assert miss.returned == (92, 92)

    def test_every_record_is_asked_about_at_the_given_limit(self):
        retrieve = _FakeRetrieve({})

        probe_titles([(1, "One"), (2, "Two")], retrieve, limit=5)

        assert retrieve.asked == [
            (overview_question("One"), 5),
            (overview_question("Two"), 5),
        ]


# --------------------------------------------------------------------------
# Against real pgvector
# --------------------------------------------------------------------------

db = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture
def space():
    EmbeddingSpace.objects.all().delete()
    return EmbeddingSpace.objects.create(
        model_id="voyage-context-4",
        dimensions=VECTOR_COLUMN_DIMENSIONS,
        metric="cosine",
        state=EmbeddingSpaceState.ACTIVE,
    )


def _record_with_vectors(space, title, count, seed=0):
    """A record with ``count`` chunks, each given a well-separated random
    vector.

    Not the deterministic fake: its vectors for similar strings sit almost on
    top of each other, so the true top-k is a near-tie and an exact and an
    approximate scan disagree legitimately. That measures the fixture, not
    the index.
    """
    import random as _random

    from apps.ai.models.chunk import DocumentChunk

    record = Record.objects.create(
        title=title, abstract="An abstract.", is_ip=False,
        dpa_accepted_at=timezone.now(),
    )
    values = tuple(
        Chunk(text=f"passage {i}", content=f"passage {i}", context_path=(),
              sequence=i, token_count=2)
        for i in range(count)
    )
    DjangoChunkRepository().save(
        record_id=record.id,
        extraction_hash=f"hash-{title}",
        chunk_set=ChunkSet(
            chunks=values, strategy_id="fixed-window", options=ChunkingOptions(),
            content_hash=chunkset_hash(values),
        ),
    )
    rng = _random.Random(seed)
    ChunkEmbedding.objects.bulk_create(
        [
            ChunkEmbedding(
                chunk=chunk, space=space,
                embedding=[rng.gauss(0, 1) for _ in range(VECTOR_COLUMN_DIMENSIONS)],
            )
            for chunk in DocumentChunk.objects.filter(chunk_set__record=record)
        ]
    )
    return record


class PlannerContextTests:
    """The two contexts that make the comparison mean anything.

    Both were written after the bug they describe. `SET LOCAL` survives a
    nested `atomic()`, so inside a test's outer transaction the flags outlived
    the block: a leaked `enable_indexscan = off` made the approximate side run
    exactly too, scoring 1.0 whatever the index did.
    """

    pytestmark = db

    def test_exact_scan_forbids_both_ways_to_reach_an_index(self):
        from apps.ai.index_health import exact_scan

        with exact_scan():
            with connection.cursor() as cursor:
                cursor.execute("SHOW enable_indexscan")
                assert cursor.fetchone()[0] == "off"
                cursor.execute("SHOW enable_bitmapscan")
                assert cursor.fetchone()[0] == "off"

    def test_index_scan_forbids_the_sequential_alternative(self):
        """Without this a small table is compared with itself, which is
        perfect recall by construction."""
        from apps.ai.index_health import index_scan

        with index_scan():
            with connection.cursor() as cursor:
                cursor.execute("SHOW enable_seqscan")
                assert cursor.fetchone()[0] == "off"

    def test_the_flags_are_restored_afterwards(self):
        from apps.ai.index_health import exact_scan, index_scan

        with exact_scan():
            pass
        with index_scan():
            pass

        with connection.cursor() as cursor:
            for flag in ("enable_indexscan", "enable_bitmapscan", "enable_seqscan"):
                cursor.execute(f"SHOW {flag}")
                assert cursor.fetchone()[0] == "on", flag

    def test_they_are_restored_even_when_the_block_raises(self):
        from apps.ai.index_health import exact_scan

        with pytest.raises(RuntimeError):
            with exact_scan():
                raise RuntimeError("boom")

        with connection.cursor() as cursor:
            cursor.execute("SHOW enable_indexscan")
            assert cursor.fetchone()[0] == "on"


@pytest.mark.usefixtures("space")
class IndexRecallTests:
    pytestmark = db

    def test_it_reports_perfect_recall_on_a_small_table(self, space):
        """A table this size is well inside what HNSW handles exactly; a
        number below 1.0 here would itself be the finding."""
        # Earlier tests' rolled-back vectors stay in the HNSW graph (nothing
        # vacuums a test database) and fill the scan; measure a fresh one.
        # TRUNCATE is transactional, so the test's rollback undoes it.
        with connection.cursor() as cursor:
            cursor.execute(f"TRUNCATE {ChunkEmbedding._meta.db_table}")
        _record_with_vectors(space, "A Thesis", 20)

        result = measure_index_recall(ChunkEmbedding, space_id=space.pk, k=5, probes=10)

        assert isinstance(result, IndexRecall)
        assert result.probes == 10
        assert result.recall == 1.0
        assert result.worst == ()
        assert result.used_index, "a seq-scan comparison would pass vacuously"

    def test_it_probes_no_more_rows_than_exist(self, space):
        _record_with_vectors(space, "A Thesis", 3)

        result = measure_index_recall(ChunkEmbedding, space_id=space.pk, k=5, probes=50)

        assert result.probes == 3

    def test_an_empty_index_is_reported_rather_than_crashing(self, space):
        result = measure_index_recall(ChunkEmbedding, space_id=space.pk, k=5, probes=10)

        assert result.probes == 0
        assert result.recall == 1.0

    def test_it_records_the_depth_it_measured_at(self, space, settings):
        """The number is only interpretable beside the depth that produced
        it — that is the whole lesson of IR-440."""
        settings.AI_HNSW_EF_SEARCH = 123
        _record_with_vectors(space, "A Thesis", 2)

        result = measure_index_recall(ChunkEmbedding, space_id=space.pk, k=2, probes=2)

        assert result.depth == 123

    def test_it_is_deterministic_for_a_given_seed(self, space):
        _record_with_vectors(space, "A Thesis", 30)

        first = measure_index_recall(
            ChunkEmbedding, space_id=space.pk, k=5, probes=5, seed=7
        )
        second = measure_index_recall(
            ChunkEmbedding, space_id=space.pk, k=5, probes=5, seed=7
        )

        assert first.probe_ids == second.probe_ids


class CommandGateTests:
    """The command's job is to *fail* when search is unhealthy. A checker that
    reports a problem and exits zero gates nothing."""

    pytestmark = db

    def test_it_refuses_when_recall_is_below_the_floor(self, space, monkeypatch):
        from django.core.management import CommandError, call_command

        monkeypatch.setattr(
            "apps.ai.management.commands.check_vector_index.measure_index_recall",
            lambda *a, **k: IndexRecall(
                label="chunk_embedding_hnsw_idx", probes=10, k=10, depth=200,
                recall=0.5, used_index=True, worst=(), probe_ids=(1,),
            ),
        )

        with pytest.raises(CommandError, match="not returning what an exact scan"):
            call_command("check_vector_index")

    def test_it_passes_at_exactly_the_floor(self, space, monkeypatch):
        from django.core.management import call_command

        monkeypatch.setattr(
            "apps.ai.management.commands.check_vector_index.measure_index_recall",
            lambda *a, **k: IndexRecall(
                label="chunk_embedding_hnsw_idx", probes=10, k=10, depth=200,
                recall=DEFAULT_MIN_RECALL, used_index=True, worst=(), probe_ids=(1,),
            ),
        )

        call_command("check_vector_index")

    def test_it_refuses_a_title_probe_with_no_user(self, space):
        """Retrieval is visibility-filtered, so a probe with no user would
        measure nothing in particular."""
        from django.core.management import CommandError, call_command

        with pytest.raises(CommandError, match="--titles needs --user"):
            call_command("check_vector_index", "--titles")

    def test_it_says_so_when_nothing_is_indexed(self):
        """An empty deployment is not a healthy one — it is an unindexed one,
        and reporting success there would be the same silent pass this whole
        ticket exists to remove."""
        from django.core.management import CommandError, call_command

        EmbeddingSpace.objects.all().delete()

        with pytest.raises(CommandError, match="No active EmbeddingSpace"):
            call_command("check_vector_index")
