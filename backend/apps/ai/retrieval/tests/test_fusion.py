"""Hybrid retrieval: the merge, the exact term, and the visibility rule (IR-395).

Three things are worth testing here and they need different machinery, so they
are three sections rather than one.

The **merge** is a pure function over two lists and is tested as one -- no
database, no user, no embedder. That is the point of ADR-033 §1 asking for it
as its own unit: sub-question merging (IR-399) and Listing questions reuse it,
and a rank-position merge buried in a retriever would have to be re-tested
through a corpus every time.

The **exact term** is tested through the real retrievers over real rows,
because the claim is about what reaches a reader, not about what a function
returns.

The **visibility rule** is tested the same way `test_visibility.py` tests the
vector path, and for the same reason: ADR-033 §Security Impact says hybrid
retrieval adds a second source of candidates and no second visibility
predicate, and the only way to hold that promise is to assert it at the seam
against a corpus the asker partly cannot read.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
from apps.ai.models.chunk import ChunkEmbedding, ChunkSet, DocumentChunk
from apps.ai.models.embedding import RecordEmbedding
from apps.ai.models.embedding_space import EmbeddingSpace
from apps.ai.providers.fakes import DeterministicEmbeddingProvider
from apps.ai.retrieval.degraded import DegradableRetriever, FullTextRetriever
from apps.ai.retrieval.fusion import KeywordFusionRetriever, fuse_by_rank
from apps.ai.retrieval.reranking import RerankingRetriever
from apps.ai.retrieval.ports import FULL_TEXT, VECTOR, RetrievalResult, RetrievedChunk, Retriever
from apps.ai.retrieval.two_stage import TwoStageRetriever
from apps.records.models import Record, RecordOwner
from core.enums import PipelineStatus
from core.permissions import ROLE_ADVISER, ROLE_KTTO, ROLE_STUDENT

User = get_user_model()
DIMENSIONS = VECTOR_COLUMN_DIMENSIONS

# The database markers sit on the classes that need one, not on the module:
# `RankMergeTests` and `DecoratorContractTests` touch no database and must run
# wherever pytest runs, the rule `pytest.ini` states for the chunking domain.


# ---------------------------------------------------------------------------
# The merge, on its own
# ---------------------------------------------------------------------------


class RankMergeTests:
    """`fuse_by_rank` given fixed lists. No corpus, no vendor, no settings."""

    def test_two_fixed_lists_interleave_by_rank_position(self):
        vector = ["v1", "v2", "v3"]
        keyword = ["k1", "k2", "k3"]

        assert fuse_by_rank((vector, keyword), key=str) == [
            "v1", "k1", "v2", "k2", "v3", "k3",
        ]

    def test_the_first_list_breaks_a_tie_at_equal_rank(self):
        """Position is the only ordering signal, so something has to break a
        tie. The list order does, which is why the retriever passes the vector
        list first: fusion is meant to add candidates, not reshuffle the ones
        already answering."""
        assert fuse_by_rank((["a"], ["b"]), key=str) == ["a", "b"]
        assert fuse_by_rank((["b"], ["a"]), key=str) == ["b", "a"]

    def test_an_item_in_both_lists_is_emitted_once_at_its_best_rank(self):
        """Being found twice can promote an item and must never demote it."""
        merged = fuse_by_rank((["a", "shared"], ["shared", "b"]), key=str)

        assert merged == ["a", "shared", "b"]
        assert merged.count("shared") == 1

    def test_a_longer_list_keeps_contributing_after_the_shorter_runs_out(self):
        assert fuse_by_rank((["v1"], ["k1", "k2", "k3"]), key=str) == [
            "v1", "k1", "k2", "k3",
        ]

    def test_an_empty_list_changes_nothing(self):
        assert fuse_by_rank((["a", "b"], []), key=str) == ["a", "b"]
        assert fuse_by_rank(([], []), key=str) == []

    def test_identity_comes_from_the_key_not_from_the_item(self):
        """The unit is reused over things that are not passages, so equality
        is the caller's to define -- IR-399's sub-question merge dedupes on the
        same chunk id across differently-scored copies."""
        items = [{"id": 1, "from": "vector"}, {"id": 1, "from": "keyword"}]

        merged = fuse_by_rank(([items[0]], [items[1]]), key=lambda i: i["id"])

        assert merged == [items[0]]


# ---------------------------------------------------------------------------
# A corpus
# ---------------------------------------------------------------------------


@pytest.fixture
def embedder():
    return DeterministicEmbeddingProvider(dimensions=DIMENSIONS)


@pytest.fixture
def space(db):
    existing = EmbeddingSpace.objects.filter(state="active").first()
    return existing or EmbeddingSpace.objects.create(
        model_id="fake-test", dimensions=DIMENSIONS, metric="cosine", state="active"
    )


def make_user(email, role_name=ROLE_STUDENT):
    from apps.accounts.models import Role

    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="x", role=role, is_verified=True
    )


def make_record(*, title, text, embedder, space, status=PipelineStatus.PUBLISHED,
                owner=None, adviser=None):
    record = Record.objects.create(title=title, pipeline_status=status, adviser=adviser)
    if owner is not None:
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
    chunk = DocumentChunk.objects.create(
        chunk_set=chunk_set, record=record, sequence=0, max_sequence=0,
        text=text, content=text, context_path=[title],
        token_count=len(text.split()), text_hash=f"t{record.pk}",
        source_page=1, element_kinds=["paragraph"], bboxes=[],
    )
    ChunkEmbedding.objects.create(
        chunk=chunk, space=space, embedding=embedder.embed_documents([text])[0]
    )
    return record


# ---------------------------------------------------------------------------
# What fusion is for
# ---------------------------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class ExactTermTests:
    """The failure ADR-033 §1 names, and the one acceptance criterion that
    says whether this ticket did anything.

    **How the miss is reproduced, stated rather than hidden.** Against Voyage
    the miss is semantic: a dense embedding blurs an uncommon token, so the
    paper naming it does not come back. `DeterministicEmbeddingProvider`
    cannot reproduce that -- it hashes words, so a shared token always lands
    close, which is exactly the property the other retrieval tests depend on.
    The miss is therefore reproduced *structurally*, by the other bound on
    what the vector path can return: stage 1 keeps a fixed number of candidate
    records, and a passage in no candidate record can never be ranked
    (`TwoStageRetriever`'s own docstring). Either way the property under test
    is the same one -- a passage the vector candidate set did not contain is
    returned with fusion on and absent with it off -- and it is the property
    the acceptance criterion asks for.
    """

    @pytest.fixture
    def corpus(self, embedder, space):
        reader = make_user("reader@cit.edu")
        # Ranks first for the question: the title shares its words.
        make_record(title="Drone Imagery Detection Survey",
                    text="a survey of drone imagery detection methods",
                    embedder=embedder, space=space, owner=reader)
        # Holds the exact term and nothing else the question says.
        make_record(title="Bridge Inspection Field Notes",
                    text="inference was run with YOLOv8 on the collected frames",
                    embedder=embedder, space=space, owner=reader)
        return reader

    #: A question about the survey's subject that also names the term only the
    #: other paper uses -- which is the shape of the real query ADR-033 §1
    #: names ("papers using YOLOv8" asked of a repository).
    QUESTION = "survey of drone imagery detection methods using YOLOv8"

    def _titles(self, retriever, reader):
        return [
            p.record_title
            for p in retriever.retrieve(self.QUESTION, reader, limit=10).passages
        ]

    def test_the_exact_term_paper_is_missing_without_fusion(self, corpus, embedder):
        """The baseline, asserted rather than assumed: without this the
        with-fusion assertion below could pass on a corpus where the vector
        path already found everything."""
        vector_only = TwoStageRetriever(embedder, record_candidates=1)

        assert "Bridge Inspection Field Notes" not in self._titles(vector_only, corpus)

    def test_the_exact_term_paper_is_returned_with_fusion_on(self, corpus, embedder):
        fused = KeywordFusionRetriever(
            TwoStageRetriever(embedder, record_candidates=1),
            keyword=FullTextRetriever(),
        )

        assert "Bridge Inspection Field Notes" in self._titles(fused, corpus)

    def test_fusion_keeps_what_the_vector_path_already_found(self, corpus, embedder):
        """Adding candidates must not cost the ones already answering."""
        fused = KeywordFusionRetriever(
            TwoStageRetriever(embedder, record_candidates=1),
            keyword=FullTextRetriever(),
        )

        assert "Drone Imagery Detection Survey" in self._titles(fused, corpus)


# ---------------------------------------------------------------------------
# The security property
# ---------------------------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class KeywordPathVisibilityTests:
    """ADR-033 §Security Impact: a second candidate source, no second rule.

    Asserted against the keyword path specifically, because that is the path
    this ticket newly puts on the healthy request. The quote the questions use
    is in every record's text, so a record missing from a result is missing
    because the asker may not read it and for no other reason.
    """

    TEXT = "weekly pond sampling of tilapia was recorded"

    @pytest.fixture
    def fused(self, embedder):
        return KeywordFusionRetriever(
            TwoStageRetriever(embedder), keyword=FullTextRetriever()
        )

    def test_a_strangers_draft_is_never_returned_by_the_keyword_path(
        self, fused, embedder, space
    ):
        author = make_user("author@cit.edu")
        make_record(title="Secret Draft", text=self.TEXT, status=PipelineStatus.DRAFT,
                    owner=author, embedder=embedder, space=space)
        stranger = make_user("stranger@cit.edu")

        assert fused.retrieve("pond sampling", stranger).passages == ()

    def test_a_readable_record_does_not_carry_its_forbidden_neighbour(
        self, fused, embedder, space
    ):
        """The case that catches filtering *after* scoring, which is the shape
        a fused list makes tempting: merge first, filter the merged list."""
        author = make_user("author@cit.edu")
        make_record(title="Public One", text=self.TEXT, embedder=embedder, space=space,
                    owner=author)
        make_record(title="Private One", text=self.TEXT, status=PipelineStatus.DRAFT,
                    owner=author, embedder=embedder, space=space)
        stranger = make_user("stranger@cit.edu")

        titles = {p.record_title for p in fused.retrieve("pond sampling", stranger).passages}
        assert titles == {"Public One"}

    def test_an_anonymous_user_receives_nothing_through_fusion(
        self, fused, embedder, space
    ):
        from django.contrib.auth.models import AnonymousUser

        author = make_user("author@cit.edu")
        make_record(title="Published Work", text=self.TEXT, embedder=embedder,
                    space=space, owner=author)

        assert fused.retrieve("pond sampling", AnonymousUser()).passages == ()

    def test_the_owner_the_adviser_and_staff_still_see_what_they_may(
        self, fused, embedder, space
    ):
        """Fusion must not narrow visibility either. A source that returned
        *less* than `visible_to` allows would be a second predicate just as
        much as one returning more."""
        author = make_user("author@cit.edu")
        adviser = make_user("adviser@cit.edu", ROLE_ADVISER)
        make_record(title="Advised Draft", text=self.TEXT, status=PipelineStatus.DRAFT,
                    owner=author, adviser=adviser, embedder=embedder, space=space)
        ktto = make_user("ktto@cit.edu", ROLE_KTTO)

        for user in (author, adviser, ktto):
            titles = [p.record_title for p in fused.retrieve("pond sampling", user).passages]
            assert titles == ["Advised Draft"], f"{user.email} lost a record they may read"


# ---------------------------------------------------------------------------
# The decorator contract
# ---------------------------------------------------------------------------


class _Fixed(Retriever):
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def retrieve(self, question, user, limit=20):
        self.calls += 1
        return self.result


def a_chunk(chunk_id: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id, record_id=chunk_id, record_title=f"Record {chunk_id}",
        content="text", context_path=(), source_page=1, score=0.5,
    )


class DecoratorContractTests:
    def test_the_inner_results_mode_and_space_survive_fusion(self):
        inner = _Fixed(RetrievalResult(
            passages=(a_chunk(1),), mode=VECTOR, embedding_space_id=7,
        ))

        result = KeywordFusionRetriever(
            inner, keyword=_Fixed(RetrievalResult(passages=(a_chunk(2),)))
        ).retrieve("q", None)

        assert (result.mode, result.embedding_space_id) == (VECTOR, 7)
        assert [p.chunk_id for p in result.passages] == [1, 2]

    def test_the_keyword_paths_degraded_flag_is_not_adopted(self):
        """`FullTextRetriever` reports `degraded=True` because its usual caller
        is the outage path. On the healthy path that flag would tell a reader
        the vendor was out while it was answering normally."""
        inner = _Fixed(RetrievalResult(passages=(a_chunk(1),), mode=VECTOR))
        keyword = _Fixed(RetrievalResult(
            passages=(a_chunk(2),), degraded=True, mode=FULL_TEXT,
        ))

        result = KeywordFusionRetriever(inner, keyword=keyword).retrieve("q", None)

        assert result.degraded is False
        assert result.mode == VECTOR

    def test_a_degraded_inner_result_is_passed_through_without_a_second_query(self):
        """The inner result already *is* full-text search, so fusing it with
        full-text search would buy a query and no candidates."""
        keyword = _Fixed(RetrievalResult(passages=(a_chunk(2),)))
        degraded = RetrievalResult(passages=(a_chunk(1),), degraded=True, mode=FULL_TEXT)

        result = KeywordFusionRetriever(_Fixed(degraded), keyword=keyword).retrieve(
            "q", None
        )

        assert result is degraded
        assert keyword.calls == 0

    def test_a_vendor_failure_beneath_fusion_still_propagates(self):
        """Degradation is `DegradableRetriever`'s decision, made outside this
        decorator. Swallowing the failure here would move it."""
        from apps.ai.resilience.circuit import CircuitOpen

        class _Failing(Retriever):
            def retrieve(self, question, user, limit=20):
                raise CircuitOpen("the vendor is out")

        with pytest.raises(CircuitOpen):
            KeywordFusionRetriever(
                _Failing(), keyword=_Fixed(RetrievalResult())
            ).retrieve("q", None)

    def test_the_callers_limit_bounds_the_fused_list(self):
        inner = _Fixed(RetrievalResult(passages=tuple(a_chunk(i) for i in range(1, 6))))
        keyword = _Fixed(RetrievalResult(
            passages=tuple(a_chunk(i) for i in range(10, 15))
        ))

        result = KeywordFusionRetriever(inner, keyword=keyword).retrieve("q", None, limit=4)

        assert len(result.passages) == 4

    def test_the_fused_score_is_monotone_with_the_merged_order(self):
        """The two input scores are a `ts_rank` and a cosine similarity, on
        different scales. `presentation.record_sources` reads the field to pick
        a record card's headline score, so a single list must not carry both --
        it carries the merged position instead, and a consumer that sorts by
        score agrees with the order it was handed."""
        inner = _Fixed(RetrievalResult(passages=(a_chunk(1), a_chunk(2))))
        keyword = _Fixed(RetrievalResult(passages=(a_chunk(3),)))

        passages = KeywordFusionRetriever(inner, keyword=keyword).retrieve(
            "q", None
        ).passages
        scores = [p.score for p in passages]

        assert scores == sorted(scores, reverse=True)
        assert len(set(scores)) == len(scores)


# ---------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------


@pytest.mark.db_required
@pytest.mark.django_db
class SwitchTests:
    """ADR-033 §5: the technique lands off, so an upgrade changes nothing.

    Asserted on the composed stack rather than on the settings module, because
    "off" means the decorator is not in the stack -- a setting read in the
    right place and then ignored would pass a settings assertion.
    """

    def _candidate_source(self):
        """What reranking is handed, reached through the public `retriever()`.

        Walked out of the real composed stack rather than asked of
        `_candidates` directly: the claim is about what a request gets, and a
        method a test calls but production does not is not that.
        """
        from apps.ai.composition import CompositionRoot
        from apps.ai.providers.noop import NoOpReranker

        root = CompositionRoot(
            embedder=DeterministicEmbeddingProvider(DIMENSIONS),
            reranker=NoOpReranker(),
        )
        degradable = root.retriever()
        assert isinstance(degradable, DegradableRetriever)
        reranking = degradable._primary
        assert isinstance(reranking, RerankingRetriever)
        return reranking._inner

    def test_fusion_is_absent_from_the_stack_by_default(self):
        assert isinstance(self._candidate_source(), TwoStageRetriever)

    @override_settings(
        AI_KEYWORD_RETRIEVAL_ENABLED=True, AI_RETRIEVAL_FUSION_ENABLED=True
    )
    def test_fusion_joins_the_stack_when_both_switches_are_on(self):
        assert isinstance(self._candidate_source(), KeywordFusionRetriever)

    @override_settings(
        AI_KEYWORD_RETRIEVAL_ENABLED=True, AI_RETRIEVAL_FUSION_ENABLED=False
    )
    def test_keyword_retrieval_alone_does_nothing(self):
        """Two settings, one technique. Searching the keyword index and then
        discarding the result is a query paid for nothing, so the half-on
        configuration is the baseline rather than something in between."""
        assert isinstance(self._candidate_source(), TwoStageRetriever)

    @override_settings(
        AI_KEYWORD_RETRIEVAL_ENABLED=False, AI_RETRIEVAL_FUSION_ENABLED=True
    )
    def test_fusion_alone_does_nothing(self):
        assert isinstance(self._candidate_source(), TwoStageRetriever)

    def test_both_settings_exist_so_the_harness_can_measure_them(self):
        """`apps/ai/evaluation/techniques.py` refuses to record a technique as
        measured while its setting is absent (IR-394). This ticket is what
        makes `--technique fusion=on` runnable at all."""
        from apps.ai.evaluation.techniques import technique

        assert technique("fusion").implemented
        assert technique("keyword_retrieval").implemented
        assert technique("fusion").value is False
        assert technique("keyword_retrieval").value is False

