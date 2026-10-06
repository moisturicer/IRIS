"""Retrieval reports why it returned nothing (IR-459).

Three facts used to collapse into one empty list: nothing was recalled,
everything was withheld by the disclosure gate, and retrieval raised. ADR-034
§2 needs them apart, and a refusal cannot otherwise be diagnosed from a log.

Four groups, in the order the ticket's acceptance criteria read:

* `ClassificationTests` -- the outcome function, **table-driven**, asserted
  total and mutually exclusive over every reachable combination. No database:
  it is a pure function over sets of ids.
* `PartitionTests` -- the four terminal buckets are disjoint and exhaustive
  over what each stage could actually observe, asserted directly on the sets
  rather than inferred from four numbers that happen to add up.
* `AbsentNotZeroTests` -- a count nobody could observe is absent.
* `CountsSurviveTests` and `NothingReachesTheWireTests` -- the counts reach
  the caller through the existing `RetrievalResult` past every decorator (the
  IR-334 lesson), and no serializer emits one.
"""

import json

import pytest
from django.urls import reverse

from apps.ai.answers.selection import SourceSelection
from apps.ai.composition import use_composition_root
from apps.ai.retrieval.degraded import DegradableRetriever, FullTextRetriever
from apps.ai.retrieval.diagnostics import (
    EMPTY,
    FAILED,
    FOUND_RELEVANT,
    FOUND_UNASSESSED,
    NONE_RELEVANT,
    OUTCOMES,
    WITHHELD_ALL,
    ChunkBuckets,
    RetrievalDiagnostics,
    classify,
)
from apps.ai.retrieval.fusion import KeywordFusionRetriever
from apps.ai.retrieval.ports import RetrievalResult, RetrievedChunk, Retriever
from apps.ai.retrieval.reranking import RerankingRetriever
from apps.ai.providers.noop import NoOpReranker
from apps.ai.providers.fakes import ScriptedReranker

from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    POND_TEXT,
    ask,
    make_record,
    make_user,
    root_with,
    search,
)


# -- the classifier, which needs nothing at all -------------------------------


def _chunk(chunk_id, record_id=1, content="text"):
    return RetrievedChunk(
        chunk_id=chunk_id,
        record_id=record_id,
        record_title="A Paper",
        content=content,
        context_path=(),
        source_page=1,
        score=0.9,
    )


class ClassificationTests:
    """The outcome function is total and mutually exclusive.

    Table-driven on purpose: the defect this ticket records is a *reachable
    combination with no applicable outcome*, and the only way to be sure there
    is none is to enumerate the combinations rather than the branches.
    """

    #: Every reachable combination of (S, withheld, below_floor, kept,
    #: assessed), named by what actually happened.
    TABLE = [
        (
            "retrieval raised, so there is no S",
            None,
            ChunkBuckets(),
            False,
            FAILED,
        ),
        (
            "nothing was recalled",
            frozenset(),
            ChunkBuckets(withheld=(), kept=(), not_selected=(), gate_evaluated=()),
            False,
            EMPTY,
        ),
        (
            "an upstream gate removed everything before selection saw it",
            frozenset(),
            ChunkBuckets(withheld=(), kept=(), not_selected=()),
            False,
            EMPTY,
        ),
        (
            "every passage presented was withheld by the gate",
            frozenset({1, 2}),
            ChunkBuckets(withheld={1, 2}, kept=(), not_selected=()),
            False,
            WITHHELD_ALL,
        ),
        (
            # Only the trimmed handful reached the gate, and all of it went.
            "the no-op reranker trimmed to 8, and all 8 were withheld",
            frozenset(range(1, 9)),
            ChunkBuckets(withheld=set(range(1, 9)), kept=(), not_selected=()),
            False,
            WITHHELD_ALL,
        ),
        (
            "survivors existed, a floor was applied, none cleared it",
            frozenset({1, 2, 3}),
            ChunkBuckets(withheld={1}, below_floor={2, 3}, kept=(), not_selected=()),
            True,
            NONE_RELEVANT,
        ),
        (
            "survivors cleared a floor",
            frozenset({1, 2, 3}),
            ChunkBuckets(withheld={1}, below_floor={2}, kept={3}, not_selected=()),
            True,
            FOUND_RELEVANT,
        ),
        (
            # The only found-case reachable today.
            "passages came back with no relevance signal available",
            frozenset({1, 2, 3}),
            ChunkBuckets(withheld=(), kept={1, 2}, not_selected={3}),
            False,
            FOUND_UNASSESSED,
        ),
        (
            "some were withheld and the rest came back unassessed",
            frozenset({1, 2, 3}),
            ChunkBuckets(withheld={1}, kept={2, 3}, not_selected=()),
            False,
            FOUND_UNASSESSED,
        ),
        (
            "the gate was switched off, so nothing was withheld",
            frozenset({1, 2}),
            ChunkBuckets(withheld=(), kept={1, 2}, not_selected=(), gate_evaluated=()),
            False,
            FOUND_UNASSESSED,
        ),
    ]

    @pytest.mark.parametrize(
        "name,presented,buckets,assessed,expected",
        TABLE,
        ids=[row[0] for row in TABLE],
    )
    def test_every_reachable_combination_has_exactly_one_outcome(
        self, name, presented, buckets, assessed, expected
    ):
        outcome = classify(presented, buckets, relevance_assessed=assessed)
        assert outcome == expected, name
        # Mutually exclusive is the stronger half: the value is one of the six
        # and `classify` returns a single value, so no input can satisfy two.
        assert outcome in OUTCOMES
        assert len([o for o in OUTCOMES if o == outcome]) == 1

    def test_the_table_covers_every_outcome_the_vocabulary_names(self):
        """A seventh outcome added without a row here fails this test.

        `none_relevant` and `found_relevant` are unreachable in production
        until IR-396 builds the floor; they are covered because the function
        must already be total over them, which is what lets that ticket add a
        floor without revisiting this classification.
        """
        covered = {row[4] for row in self.TABLE}
        assert covered == set(OUTCOMES)

    def test_the_full_recall_counts_take_no_part_in_the_classification(self):
        """The reachable no-outcome state the ticket records.

        A hundred candidates recalled, eight trimmed to the gate, all eight
        withheld. Tying classification to the recall counts leaves withheld
        (8) nowhere near recalled (100), nothing kept, and -- with no floor --
        every outcome false. Over the selection stage alone it is one value.
        """
        selection = ChunkBuckets(
            withheld=set(range(1, 9)), kept=(), not_selected=()
        )
        recall = ChunkBuckets(
            withheld=(), kept=set(range(1, 9)), not_selected=set(range(9, 101)),
            gate_evaluated=(),
        )
        diagnostics = RetrievalDiagnostics(
            outcome=classify(frozenset(range(1, 9)), selection),
        )
        assert diagnostics.outcome == WITHHELD_ALL
        # And the recall counts really are a different, non-contributing set.
        assert classify(frozenset(range(1, 9)), recall) == FOUND_UNASSESSED

    def test_a_failed_retrieval_is_classified_without_a_bucket(self):
        diagnostics = RetrievalDiagnostics.failed()
        assert diagnostics.outcome == FAILED
        assert set(diagnostics.selection.buckets.counts.values()) == {None}


class PartitionTests:
    """The four terminal buckets are disjoint and exhaustive."""

    def test_a_chunk_in_two_buckets_is_reported_as_an_overlap(self):
        """The check itself has to work, or the assertions below prove nothing."""
        buckets = ChunkBuckets(withheld={1, 2}, kept={2}, not_selected=())
        assert buckets.overlaps == {("withheld", "kept"): frozenset({2})}

    def test_the_selection_buckets_partition_exactly_what_was_presented(self):
        """Disjoint and exhaustive over what selection could observe -- which
        is the passages retrieval handed it, and nothing else."""
        presented = [_chunk(i, record_id=i) for i in range(1, 6)]
        selection = SourceSelection(
            permits=lambda record: True, policy_enabled=False, max_sources=2
        )
        diagnostics = selection.select(
            RetrievalResult(passages=tuple(presented))
        ).diagnostics
        buckets = diagnostics.selection.buckets

        assert buckets.overlaps == {}
        assert buckets.observed == frozenset(range(1, 6))
        assert buckets.counts["kept"] == 2
        assert buckets.counts["not_selected"] == 3

    @pytest.mark.django_db
    @pytest.mark.db_required
    def test_a_gate_that_removes_everything_partitions_into_withheld_alone(self):
        presented = [_chunk(i, record_id=i) for i in range(1, 4)]
        selection = SourceSelection(
            permits=lambda record: False, policy_enabled=True, max_sources=8
        )
        diagnostics = selection.select(
            RetrievalResult(passages=tuple(presented))
        ).diagnostics

        assert diagnostics.outcome == WITHHELD_ALL
        buckets = diagnostics.selection.buckets
        assert buckets.overlaps == {}
        assert buckets.withheld == frozenset(range(1, 4))
        assert buckets.observed == frozenset(range(1, 4))


class AbsentNotZeroTests:
    """A count nobody could observe is absent, never zero."""

    @pytest.mark.django_db
    @pytest.mark.db_required
    def test_no_relevance_floor_exists_so_below_floor_is_absent(self):
        selection = SourceSelection(permits=lambda record: True, policy_enabled=True)
        diagnostics = selection.select(
            RetrievalResult(passages=(_chunk(1),))
        ).diagnostics
        assert diagnostics.selection.buckets.below_floor is None
        assert diagnostics.selection.buckets.counts["below_floor"] is None

    def test_the_degraded_path_reports_no_recall_counts_at_all(self):
        """There is no reranker on the outage path, so there is no recall
        stage to have observed anything -- as distinct from one that observed
        nothing.
        """
        result = RetrievalResult(degraded=True, mode="full-text")
        assert not result.diagnostics.observed_anything
        assert set(result.diagnostics.buckets.counts.values()) == {None}

    def test_a_gate_that_ran_on_nothing_reports_zero_not_absent(self):
        """The other side of the same rule. With the no-op reranker the
        upstream gate evaluates nothing -- an observed zero, not an absence.
        """
        buckets = ChunkBuckets(
            withheld=(), kept={1}, not_selected=(), gate_evaluated=()
        )
        assert buckets.counts["gate_evaluated"] == 0
        assert buckets.counts["withheld"] == 0


# -- the counts survive the stack, and never leave it -------------------------


class _Fixed(Retriever):
    """A retriever whose result is handed in, so a decorator is the only
    thing under test."""

    def __init__(self, result: RetrievalResult) -> None:
        self._result = result

    def retrieve(self, question, user, limit=20):
        return self._result


class _Raising(Retriever):
    def retrieve(self, question, user, limit=20):
        raise ValueError("a bug in our own query, not a vendor outage")


class _TransmittingReranker(ScriptedReranker):
    """`ScriptedReranker` declares it transmits nothing, which is true of every
    test double -- and it means the recall-stage gate never runs under one. The
    gate branches on this flag, so exercising it needs a double that claims to
    transmit."""

    transmits_externally = True


class CountsSurviveTests:
    """The IR-334 lesson: a field computed inside a decorator and returned any
    other way is a field the next decorator drops."""

    def test_reranking_records_what_it_recalled_gated_and_trimmed(self):
        candidates = tuple(_chunk(i, record_id=1) for i in range(1, 6))
        retriever = RerankingRetriever(
            _Fixed(RetrievalResult(passages=candidates, mode="vector")),
            reranker=NoOpReranker(),
            recall_limit=100,
            policy_enabled=True,
        )

        diagnostics = retriever.retrieve("q", None, limit=2).diagnostics

        assert diagnostics.buckets.counts["kept"] == 2
        assert diagnostics.buckets.counts["not_selected"] == 3
        # A no-op reranker transmits nothing, so the gate runs on nothing.
        assert diagnostics.buckets.counts["gate_evaluated"] == 0
        assert diagnostics.buckets.counts["withheld"] == 0
        assert diagnostics.configuration.recall_limit == 100
        assert diagnostics.configuration.requested_limit == 2
        assert diagnostics.configuration.reranker == "NoOpReranker"
        assert diagnostics.configuration.reranker_transmits is False
        assert diagnostics.configuration.disclosure_gate is False
        assert diagnostics.configuration.mode == "vector"

    def test_the_configuration_is_recorded_beside_the_counts(self):
        """The counts mean different things under different settings, so a
        reader of one needs the other."""
        retriever = RerankingRetriever(
            _Fixed(
                RetrievalResult(
                    passages=(_chunk(1),), mode="vector", embedding_space_id=7
                )
            ),
            reranker=ScriptedReranker(),
            recall_limit=50,
        )

        configuration = retriever.retrieve(
            "q", None, limit=8
        ).diagnostics.configuration

        assert configuration.embedding_space_id == 7
        assert configuration.reranker == "ScriptedReranker"
        assert configuration.reranker_transmits is False
        assert configuration.disclosure_gate is False
        assert configuration.recall_limit == 50

    def test_degradation_carries_the_inner_report_through_unchanged(self):
        inner = RerankingRetriever(
            _Fixed(RetrievalResult(passages=(_chunk(1),), mode="vector")),
            reranker=NoOpReranker(),
        )
        expected = inner.retrieve("q", None, limit=8).diagnostics

        carried = DegradableRetriever(inner).retrieve("q", None, limit=8).diagnostics

        assert carried == expected

    def test_fusion_inside_reranking_does_not_reset_the_report(self):
        """`KeywordFusionRetriever` returns `inner.with_passages(...)`, so its
        own stage has no counts and must not blank the ones already there."""
        fused = KeywordFusionRetriever(
            _Fixed(RetrievalResult(passages=(_chunk(1),), mode="vector")),
            keyword=_Fixed(RetrievalResult(passages=(_chunk(2, record_id=2),))),
        )
        retriever = RerankingRetriever(
            fused, reranker=NoOpReranker(), recall_limit=100
        )

        diagnostics = retriever.retrieve("q", None, limit=8).diagnostics

        assert diagnostics.buckets.counts["kept"] == 2
        assert diagnostics.configuration.recall_limit == 100

    def test_a_blank_full_text_search_still_reports_an_absent_recall_stage(self):
        result = FullTextRetriever().retrieve("   ", None)
        assert result.degraded is True
        assert not result.diagnostics.observed_anything

    @pytest.mark.django_db
    @pytest.mark.db_required
    def test_the_recall_gate_records_only_candidates_it_actually_ran_on(
        self, embedder, space
    ):
        """A chunk is never counted as withheld because it *would* have been
        removed. The gate ran here, so the count is real."""
        record = make_record(title="Flood Prediction", text=FLOOD_TEXT,
                             embedder=embedder, space=space)
        candidates = tuple(_chunk(i, record_id=record.pk) for i in range(1, 4))
        retriever = RerankingRetriever(
            _Fixed(RetrievalResult(passages=candidates, mode="vector")),
            reranker=_TransmittingReranker(),
            permits=lambda rec: False,
        )

        buckets = retriever.retrieve("q", None, limit=8).diagnostics.buckets

        assert buckets.counts["gate_evaluated"] == 3
        assert buckets.withheld == frozenset({1, 2, 3})
        assert buckets.counts["kept"] == 0
        assert buckets.overlaps == {}
        assert buckets.observed == frozenset({1, 2, 3})


@pytest.mark.django_db
@pytest.mark.db_required
class SelectionOverTheRealStackTests:
    """The outcome, computed where it is computed in production."""

    def test_a_question_with_sources_is_found_but_unassessed(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        root = root_with(embedder=embedder)

        with use_composition_root(root):
            result = root.retriever().retrieve(FLOOD_QUESTION, reader, limit=8)
            diagnostics = root.source_selection(8).select(result).diagnostics

        assert diagnostics.outcome == FOUND_UNASSESSED
        assert diagnostics.selection.buckets.counts["kept"] >= 1
        # The recall stage ran here, so its counts are present rather than absent.
        assert diagnostics.recall.observed_anything

    def test_a_corpus_the_gate_refuses_is_withheld_all_not_empty(
        self, embedder, space, client_for
    ):
        """The distinction this ticket exists for. Both answer `no_sources`
        to a reader; only one of them found nothing.
        """
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        root = root_with(embedder=embedder)

        with use_composition_root(root):
            result = root.retriever().retrieve(FLOOD_QUESTION, reader, limit=8)

        refusing = SourceSelection(
            permits=lambda record: False, policy_enabled=True, max_sources=8
        )
        assert refusing.select(result).diagnostics.outcome == WITHHELD_ALL

        allowing = SourceSelection(
            permits=lambda record: True, policy_enabled=True, max_sources=8
        )
        empty = RetrievalResult(mode="vector")
        assert allowing.select(empty).diagnostics.outcome == EMPTY

    def test_a_retrieval_that_raises_is_logged_as_failed_and_re_raised(
        self, embedder, space, monkeypatch
    ):
        """`failed` is distinguishable, and distinguishing it changes nothing:
        a bug in our own query still reaches the caller.

        The module logger is swapped rather than read through `caplog`: this
        project's `LOGGING` does not propagate `apps.ai` to the root logger,
        so the record is emitted and `caplog` never sees it.
        """
        from apps.ai.answers import service as service_module
        from apps.ai.providers.fakes import ScriptedLLM

        warnings = []
        monkeypatch.setattr(
            service_module.logger,
            "warning",
            lambda message, *args, **kwargs: warnings.append(message % args),
        )
        service = service_module.GroundedAnswerService(
            retriever=_Raising(), llm=ScriptedLLM(), permits=lambda record: True
        )

        with pytest.raises(ValueError):
            service.answer("anything", make_user("reader@cit.edu"))

        assert any(FAILED in line for line in warnings)

    def test_the_answer_path_records_the_outcome_it_acted_on(
        self, embedder, space
    ):
        from apps.ai.answers.service import GroundedAnswerService
        from apps.ai.providers.fakes import ScriptedLLM

        reader = make_user("reader@cit.edu")
        make_record(title="Tilapia Ponds", text=POND_TEXT,
                    embedder=embedder, space=space)
        root = root_with(embedder=embedder)
        service = GroundedAnswerService(
            retriever=root.retriever(),
            llm=ScriptedLLM(),
            permits=lambda record: False,
        )

        _retrieved, sources, diagnostics = service._retrieve_and_gate(
            "tilapia", reader
        )

        assert sources == []
        assert diagnostics.outcome == WITHHELD_ALL


@pytest.mark.django_db
@pytest.mark.db_required
class NothingReachesTheWireTests:
    """No reader-visible change and no API change.

    Asserted over serializer and response output rather than trusted to
    convention: the counts say which records were withheld from whom, and an
    accidental key is the one way this ticket could become a disclosure.
    """

    #: Every name a count could travel under, including the outcome itself.
    FORBIDDEN = (
        "withheld",
        "below_floor",
        "not_selected",
        "gate_evaluated",
        "diagnostics",
        "outcome",
        "withheld_all",
        "found_unassessed",
        "none_relevant",
    )

    def _assert_clean(self, payload):
        body = json.dumps(payload)
        leaked = [name for name in self.FORBIDDEN if name in body]
        assert leaked == [], f"{leaked} reached the wire: {body[:400]}"

    def test_the_ask_response_carries_no_count_or_outcome(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            response = ask(client_for(reader), FLOOD_QUESTION)

        assert response.status_code == 200
        self._assert_clean(response.json())

    def test_a_withheld_everything_ask_still_looks_like_no_sources(
        self, embedder, space, client_for
    ):
        """The boundary stays indistinguishable, which is IR-460's decision
        and not this ticket's to change (IR-153)."""
        from apps.ai.composition import CompositionRoot
        from apps.ai.providers.fakes import ScriptedLLM, ScriptedReranker

        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        refusing = CompositionRoot(
            embedder=embedder,
            reranker=ScriptedReranker(),
            llm=ScriptedLLM(),
            permits=lambda record: False,
        )

        with use_composition_root(refusing):
            body = ask(client_for(reader), FLOOD_QUESTION).json()

        assert body["mode"] == "no_results"
        assert body["answer"] is None
        self._assert_clean(body)

    def test_the_search_response_carries_no_count_either(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)

        with use_composition_root(root_with(embedder=embedder)):
            response = search(client_for(reader), FLOOD_QUESTION)

        assert response.status_code == 200
        self._assert_clean(response.json())

    def test_a_replayed_transcript_carries_no_count(
        self, embedder, space, client_for
    ):
        reader = make_user("reader@cit.edu")
        make_record(title="Flood Prediction", text=FLOOD_TEXT,
                    embedder=embedder, space=space)
        client = client_for(reader)
        conversation_id = client.post(
            reverse("ai-conversations"), {}, format="json"
        ).json()["id"]

        with use_composition_root(root_with(embedder=embedder)):
            ask(client, FLOOD_QUESTION, conversation_id=conversation_id)

        response = client.get(
            reverse("ai-conversation-detail", args=[conversation_id])
        )
        assert response.status_code == 200
        self._assert_clean(response.json())
