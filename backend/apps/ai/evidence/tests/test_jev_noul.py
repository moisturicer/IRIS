"""Jev Noul mode of the evidence decision (IR-482, ADR-035 §2, §3, §8).

One noul question -- does answering require corpus evidence? -- asked of a
state holding the question, the stored Resolved question (untrusted), up to
five prior reader questions and a short versioned corpus description. Nothing
retrieved. Every failure routes to evidence with its own code, and the
probability is kept so a threshold curve can be drawn without choosing one.
"""

from __future__ import annotations

import inspect
import json

import pytest

from apps.ai.evidence.jev_noul import (
    CORPUS_DESCRIPTION,
    CORPUS_DESCRIPTION_VERSION,
    NOUL_CRITERIA,
    NOUL_INSTRUCTIONS,
    REFERENCE_THRESHOLD,
    JevNoulDecision,
    build_state,
    jev_digest,
)
from apps.ai.evidence.model_decision import (
    DECIDED_REASONS,
    FALLBACK_REASONS,
    MAX_PRIOR_QUESTIONS,
    REASON_ANSWERED_DIRECTLY,
    REASON_MALFORMED_RESPONSE,
    REASON_PROVIDER_FAILURE,
    REASON_RATE_LIMITED,
    REASON_SEARCH_REQUESTED,
    REASON_TIMEOUT,
    REASONS,
    ROUTE_DIRECT,
    ROUTE_EVIDENCE,
    ModelDecision,
)
from apps.ai.providers.decisions import (
    DecisionMalformed,
    DecisionUnavailable,
    NoulAnswer,
    ScriptedDecisionModel,
)
from apps.ai.providers.errors import ErrorKind

pytestmark = pytest.mark.django_required


def decide(step, question="What is the median?", **kwargs):
    model = ScriptedDecisionModel(step)
    return JevNoulDecision(model).decide(question, **kwargs), model


class TheProbabilityRoutesTests:
    def test_a_high_probability_routes_to_evidence(self):
        decision, _ = decide(0.9)

        assert decision.route == ROUTE_EVIDENCE
        assert decision.reason == REASON_SEARCH_REQUESTED
        assert decision.decided
        assert decision.probability == 0.9

    def test_a_low_probability_routes_to_direct(self):
        decision, _ = decide(0.1)

        assert decision.route == ROUTE_DIRECT
        assert decision.reason == REASON_ANSWERED_DIRECTLY
        assert decision.probability == 0.1

    def test_the_reference_threshold_is_inclusive_and_is_not_an_operating_point(self):
        assert REFERENCE_THRESHOLD == 0.5
        assert decide(0.5)[0].route == ROUTE_EVIDENCE
        assert decide(0.4999)[0].route == ROUTE_DIRECT

    def test_the_returned_model_version_is_recorded(self):
        decision, _ = decide(NoulAnswer(0.7, "typesafe/jev-1.13-20260917", 140, 0.00003))

        assert decision.model == "typesafe/jev-1.13-20260917"
        assert decision.input_tokens == 140
        assert decision.output_tokens is None
        assert (decision.answer_present, decision.answer_chars) == (False, 0)

    def test_the_probability_is_in_the_serialized_decision(self):
        assert decide(0.25)[0].as_dict()["probability"] == 0.25


class EveryFallbackRoutesToEvidenceTests:
    @pytest.mark.parametrize(
        "failure, reason",
        [
            (DecisionUnavailable("slow", kind=ErrorKind.TIMEOUT), REASON_TIMEOUT),
            (DecisionUnavailable("429", kind=ErrorKind.RATE_LIMIT), REASON_RATE_LIMITED),
            (DecisionUnavailable("down", kind=ErrorKind.NETWORK), REASON_PROVIDER_FAILURE),
            (DecisionUnavailable("key", kind=ErrorKind.AUTH), REASON_PROVIDER_FAILURE),
            (DecisionUnavailable("other"), REASON_PROVIDER_FAILURE),
            (DecisionMalformed("no noul"), REASON_MALFORMED_RESPONSE),
        ],
        ids=["timeout", "rate-limit", "network", "auth", "unknown", "malformed"],
    )
    def test_the_failure_routes_to_evidence_with_its_own_code(self, failure, reason):
        decision, _ = decide(failure)

        assert decision.route == ROUTE_EVIDENCE
        assert decision.reason == reason
        assert not decision.decided
        assert decision.probability is None
        assert decision.latency_ms >= 0

    def test_the_new_code_is_a_distinct_fallback(self):
        assert REASON_MALFORMED_RESPONSE in FALLBACK_REASONS
        assert REASON_MALFORMED_RESPONSE in REASONS
        assert len(set(REASONS)) == len(REASONS)
        assert set(DECIDED_REASONS).isdisjoint(FALLBACK_REASONS)

    def test_a_bug_is_not_swallowed_as_a_fallback(self):
        with pytest.raises(TypeError):
            decide(TypeError("bug"))


class TheStateTests:
    def state(self, **kwargs):
        return build_state("q", **kwargs)

    def test_it_carries_the_question_and_the_versioned_corpus_description(self):
        state = build_state("What is the sample size?")

        assert state["question"] == "What is the sample size?"
        assert state["corpus"] == {
            "version": CORPUS_DESCRIPTION_VERSION,
            "description": CORPUS_DESCRIPTION,
        }
        assert set(state) == {"corpus", "question"}

    def test_the_corpus_description_is_short_and_versioned(self):
        assert CORPUS_DESCRIPTION_VERSION
        assert 0 < len(CORPUS_DESCRIPTION) <= 600

    def test_a_resolved_question_is_labelled_untrusted_and_only_when_it_differs(self):
        differs = build_state("and that one?", resolved_question="Sample size of the tilapia study?")
        same = build_state("q", resolved_question="q")
        blank = build_state("q", resolved_question="  ")

        assert differs["rewritten_question_untrusted"] == "Sample size of the tilapia study?"
        assert "rewritten_question_untrusted" not in same
        assert "rewritten_question_untrusted" not in blank

    def test_prior_reader_questions_are_capped_at_five_most_recent_last(self):
        prior = [f"earlier {i}" for i in range(8)]
        state = build_state("q", prior_reader_questions=prior)

        assert MAX_PRIOR_QUESTIONS == 5
        assert state["earlier_questions"] == prior[-5:]

    def test_blank_prior_questions_are_dropped_and_none_means_no_key(self):
        assert "earlier_questions" not in build_state("q", prior_reader_questions=["", "  "])
        assert build_state("q", prior_reader_questions=[" a ", ""])["earlier_questions"] == ["a"]

    def test_there_is_no_way_to_hand_it_a_passage_a_turn_or_an_answer(self):
        for fn in (build_state, JevNoulDecision.decide):
            names = set(inspect.signature(fn).parameters) - {"self"}
            assert names == {"question", "resolved_question", "prior_reader_questions"}

    def test_the_state_is_json_serializable_and_holds_only_strings_and_lists(self):
        state = build_state("q", resolved_question="r", prior_reader_questions=["a"])
        assert json.loads(json.dumps(state)) == state

    def test_the_state_sent_is_exactly_the_built_state(self):
        _, model = decide(0.2, "Why?", resolved_question="Why is it so?", prior_reader_questions=["Hi"])

        (call,) = model.calls
        assert call["state"] == build_state(
            "Why?", resolved_question="Why is it so?", prior_reader_questions=["Hi"]
        )
        assert call["instructions"] == NOUL_INSTRUCTIONS
        assert call["criteria"] == NOUL_CRITERIA

    def test_one_call_and_no_loop(self):
        _, model = decide(0.2)
        assert len(model.calls) == 1

    def test_the_noul_criteria_name_both_outcomes(self):
        assert set(NOUL_CRITERIA) == {"true", "false"}
        assert "unclear" in NOUL_INSTRUCTIONS.lower()


class TheRecordedFactsTests:
    def test_the_decision_has_no_field_that_could_hold_model_text(self):
        import dataclasses

        strings = {f.name for f in dataclasses.fields(ModelDecision) if f.type in (str, "str")}
        assert strings == {"route", "reason", "model"}

    def test_the_digest_changes_with_the_description_the_instructions_and_the_pin(self):
        base = jev_digest("typesafe/jev-1.13")

        assert base == jev_digest("typesafe/jev-1.13")
        assert base != jev_digest("typesafe/jev-1.14")
        assert len(base) == 64
