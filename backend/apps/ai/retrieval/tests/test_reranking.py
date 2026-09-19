"""Reranking wired into retrieval (IR-130).

Three properties, and the order they happen in is the point:

1. recall is **widened** before reranking, because reranking whatever stage 2
   already narrowed to achieves nothing;
2. anything the disclosure policy refuses is dropped **before** the reranker
   is called, never filtered out of its results -- filtering afterwards means
   the content has already left the deployment;
3. swapping `NoOpReranker` for a real one is configuration, not a code path,
   which is what lets IR-133 measure whether reranking earns its cost.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider, ScriptedReranker
from apps.ai.providers.noop import NoOpReranker
from apps.ai.providers.ports import RerankedCandidate, Reranker
from apps.ai.retrieval.reranking import RerankingRetriever
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_STUDENT

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

User = get_user_model()
DIMENSIONS = VECTOR_COLUMN_DIMENSIONS


class _TransmittingReranker(Reranker):
    """Stands in for Voyage: declares that it transmits, and records what it
    was handed, so a test can assert what did and did not leave."""

    transmits_externally = True

    def __init__(self):
        self.seen = []

    def rerank(self, query, candidates):
        self.seen.append(list(candidates))
        return [
            RerankedCandidate(index=i, text=t, score=float(len(candidates) - i))
            for i, t in enumerate(candidates)
        ]


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


def make_record(title, owner, embedder, space, texts, *, is_ip=False, consented=True):
    record = Record.objects.create(
        title=title,
        pipeline_status=PipelineStatus.PUBLISHED,
        is_ip=is_ip,
        dpa_accepted_at=timezone.now() if consented else None,
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    RecordEmbedding.objects.create(
        record=record,
        embedding=embedder.embed_documents([title])[0],
        model_name="fake-test",
    )
    chunk_set = ChunkSet.objects.create(
        record=record, extraction_hash="h", strategy_id="s",
        options={}, content_hash=f"c{record.pk}", is_active=True,
    )
    for i, text in enumerate(texts):
        chunk = DocumentChunk.objects.create(
            chunk_set=chunk_set, record=record, sequence=i,
            max_sequence=len(texts) - 1, text=text, content=text,
            context_path=[title], token_count=len(text.split()),
            text_hash=f"h{record.pk}{i}", source_page=1,
            element_kinds=["paragraph"], bboxes=[],
        )
        ChunkEmbedding.objects.create(
            chunk=chunk, space=space, embedding=embedder.embed_documents([text])[0]
        )
    return record


class RecallWideningTests:
    def test_reranking_sees_more_candidates_than_the_caller_asked_for(
        self, embedder, space, reader
    ):
        """Retrieving a handful and reranking that handful achieves nothing.
        Recall is cheap in Postgres; precision is what the reranker sells, and
        it needs something to improve on."""
        make_record("Thesis", reader, embedder, space,
                    [f"passage number {i}" for i in range(30)])
        spy = _TransmittingReranker()

        RerankingRetriever(
            TwoStageRetriever(embedder), reranker=spy,
            recall_limit=25, policy_enabled=False,
        ).retrieve("passage", reader, limit=3)

        assert len(spy.seen[0]) > 3, "the reranker was handed only what was asked for"

    def test_the_callers_limit_still_bounds_the_result(self, embedder, space, reader):
        make_record("Thesis", reader, embedder, space,
                    [f"passage number {i}" for i in range(30)])

        results = RerankingRetriever(
            TwoStageRetriever(embedder), reranker=NoOpReranker(), recall_limit=25
        ).retrieve("passage", reader, limit=3)

        assert len(results.passages) == 3


class DisclosureGateTests:
    def test_refused_content_never_reaches_a_transmitting_reranker(
        self, embedder, space, reader
    ):
        """Filtering the reranker's *output* would be too late -- the text has
        already left the deployment by then."""
        make_record("IP Work", reader, embedder, space, ["a secret passage"], is_ip=True)
        spy = _TransmittingReranker()

        RerankingRetriever(
            TwoStageRetriever(embedder), reranker=spy, policy_enabled=True
        ).retrieve("passage", reader)

        sent = [text for call in spy.seen for text in call]
        assert "a secret passage" not in sent

    def test_a_local_reranker_is_not_gated_because_nothing_leaves(
        self, embedder, space, reader
    ):
        """The gate exists to stop content reaching a commercial vendor.
        `NoOpReranker` makes no outbound call, so withholding candidates from
        it protects nobody and costs recall."""
        make_record("IP Work", reader, embedder, space, ["a secret passage"], is_ip=True)

        results = RerankingRetriever(
            TwoStageRetriever(embedder), reranker=NoOpReranker(), policy_enabled=True
        ).retrieve("passage", reader)

        assert [p.content for p in results.passages] == ["a secret passage"]

    def test_permitted_content_still_reaches_a_transmitting_reranker(
        self, embedder, space, reader
    ):
        """The gate must be capable of *allowing*, or the test above would pass
        against a gate that refuses everything for the wrong reason -- which,
        until IR-250 adds an embargo field, is exactly what it does."""
        make_record("Open Work", reader, embedder, space, ["an open passage"])
        spy = _TransmittingReranker()

        RerankingRetriever(
            TwoStageRetriever(embedder), reranker=spy, policy_enabled=True,
            permits=lambda record: True,
        ).retrieve("passage", reader)

        assert "an open passage" in [t for call in spy.seen for t in call]


class SubstitutabilityTests:
    def test_switching_the_reranker_changes_no_call_site(self, embedder, space, reader):
        """Same construction, same call, two rerankers."""
        make_record("Thesis", reader, embedder, space,
                    ["weekly pond sampling", "budget narrative"])
        inner = TwoStageRetriever(embedder)

        for reranker in (NoOpReranker(), ScriptedReranker()):
            results = RerankingRetriever(
                inner, reranker=reranker, policy_enabled=False
            ).retrieve("weekly pond sampling", reader, limit=2)
            assert len(results.passages) == 2

    def test_a_real_reranker_puts_the_best_match_first(self, embedder, space, reader):
        """IR-133 measures whether reranking earns its cost; both arms have to
        be reachable the same way for that comparison to mean anything."""
        make_record("Thesis", reader, embedder, space,
                    ["budget narrative", "weekly pond sampling"])
        inner = TwoStageRetriever(embedder)

        reranked = RerankingRetriever(
            inner, reranker=ScriptedReranker(), policy_enabled=False
        ).retrieve("weekly pond sampling", reader)

        assert reranked.passages[0].content == "weekly pond sampling"

    def test_the_no_op_arm_preserves_the_retrievers_own_order(
        self, embedder, space, reader
    ):
        make_record("Thesis", reader, embedder, space,
                    ["budget narrative", "weekly pond sampling"])
        inner = TwoStageRetriever(embedder)

        baseline = [
            p.content
            for p in inner.retrieve("weekly pond sampling", reader).passages
        ]
        through_noop = [
            p.content
            for p in RerankingRetriever(
                inner, reranker=NoOpReranker(), policy_enabled=False
            ).retrieve("weekly pond sampling", reader).passages
        ]

        assert through_noop == baseline


class CachingTests:
    def test_the_same_question_over_the_same_candidates_reranks_once(
        self, embedder, space, reader
    ):
        make_record("Thesis", reader, embedder, space, ["a passage"])
        spy = _TransmittingReranker()
        retriever = RerankingRetriever(
            TwoStageRetriever(embedder), reranker=spy,
            policy_enabled=False, cache={},
        )

        retriever.retrieve("passage", reader)
        retriever.retrieve("passage", reader)

        assert len(spy.seen) == 1, "the second call should have been served from cache"

    def test_a_different_candidate_set_is_a_different_cache_entry(
        self, embedder, space, reader
    ):
        """Keyed on the question *and* the candidate ids: the same question
        over a changed corpus is a different reranking, and serving the old
        one would rank passages that are no longer there."""
        make_record("Thesis", reader, embedder, space, ["a passage"])
        spy = _TransmittingReranker()
        retriever = RerankingRetriever(
            TwoStageRetriever(embedder), reranker=spy,
            policy_enabled=False, cache={},
        )

        retriever.retrieve("passage", reader)
        make_record("Second", reader, embedder, space, ["another passage"])
        retriever.retrieve("passage", reader)

        assert len(spy.seen) == 2
