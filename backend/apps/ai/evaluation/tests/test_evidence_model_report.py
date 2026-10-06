"""The model's route beside the detector's, in the curated instrument (IR-465).

ADR-035 §10: detector results and model decisions are separate sections and are
never one number. Pure: the model is `ScriptedToolCallingLLM`, so these run
anywhere and spend nothing.
"""

import json

import pytest

from apps.ai.evaluation.evidence import run_curated
from apps.ai.evaluation.labels import parse_question_set
from apps.ai.evidence.detector import EvidenceDetector
from apps.ai.evidence.model_decision import (
    REASON_RATE_LIMITED,
    REASON_SEARCH_REQUESTED,
    ModelEvidenceDecision,
)
from apps.ai.evidence.rules import build_rule_set
from apps.ai.providers.errors import ErrorKind
from apps.ai.providers.fakes import ScriptedToolCallingLLM
from apps.ai.providers.openai_compatible import LLMUnavailable

pytestmark = pytest.mark.django_required

QUOTE = "the document stopped moving and nobody noticed that it had"
CALL = ScriptedToolCallingLLM.calling
ANSWER = ScriptedToolCallingLLM.answering


@pytest.fixture
def detector():
    return EvidenceDetector(build_rule_set(institution_terms=("CIT-U",)))


def q(qid, text, evidence, **extra):
    return {
        "id": qid,
        "question": text,
        "evidence_required": evidence,
        "expected_outcome": "answer",
        "expected": [] if evidence == "none" else [{"record": "A", "quote": QUOTE}],
        **extra,
    }


def questions(*items):
    return parse_question_set({"name": "t", "questions": list(items)})


def model_for(script):
    """A decider whose reply is a function of the question asked."""
    return ModelEvidenceDecision(
        ScriptedToolCallingLLM(lambda request: script(request.user))
    )


def by_text(**routes):
    """Reply with a search or an answer by a word in the question."""

    def script(user):
        for word, step in routes.items():
            if word in user:
                return step
        raise AssertionError(f"no scripted reply for {user!r}")

    return script


@pytest.fixture
def mixed():
    """Four questions covering every cell of the detector/model grid.

    needs-corpus  detector  model
    paper         yes       yes   -> both evidence
    vague         no        yes   -> model only
    median        no        no    -> both direct
    sneaky        no        no    -> both direct but needs the corpus: a UNION miss
    cit           yes       no    -> detector only (over-fire on a general question)
    """
    return questions(
        q("q1", "what did the paper find?", "corpus"),
        q("q2", "what exactly did they say?", "corpus"),
        q("q3", "what is a median?", "none"),
        q("q4", "how does the loop handle failures?", "corpus"),
        q("q5", "what is a CIT-U?", "none"),
    )


@pytest.fixture
def script():
    return by_text(
        paper=CALL(),
        exactly=CALL(),
        median=ANSWER("A middle value."),
        loop=ANSWER("It retries."),
        CIT=ANSWER("An institution."),
    )


class WithoutADeciderTests:
    def test_the_model_section_stays_null(self, detector, mixed):
        report = run_curated(detector, mixed)

        assert report.model is None
        assert report.as_dict()["model"] is None
        assert "Model decisions: none" in report.render()
        assert "--model-decision" in report.render()


class TheModelSectionTests:
    @pytest.fixture
    def report(self, detector, mixed, script):
        return run_curated(detector, mixed, decider=model_for(script))

    def test_it_is_a_separate_section_from_the_detectors(self, report):
        data = report.as_dict()

        assert set(data["detector"]) == {"lanes", "categories", "institutional"}
        assert data["model"]["questions"] == 5
        assert "model_alone" in data["model"] and "union" in data["model"]
        assert "model_alone" not in data["detector"]

    def test_the_model_alone_is_scored_against_the_label(self, report):
        alone = report.model.alone

        assert alone["judged"] == 5
        assert alone["missed_searches"] == ["q4"]
        assert alone["over_searches"] == []
        assert alone["correct"] == 4

    def test_agreement_with_the_detector_is_counted_in_every_cell(self, report):
        agreement = report.model.agreement

        assert agreement["both_evidence"] == 1  # q1
        assert agreement["model_only_evidence"] == 1  # q2
        assert agreement["both_direct"] == 2  # q3, q4
        assert agreement["detector_only_evidence"] == 1  # q5
        assert agreement["agreement"] == pytest.approx(0.6)

    def test_the_union_misses_what_neither_half_caught(self, report):
        """ADR-035 §3: a direct answer needs both to permit it. q4 is the
        `s02` shape: neither half catches it."""
        union = report.model.union

        assert union["missed_searches"] == ["q4"]
        assert union["over_searches"] == ["q5"]
        # The detector's over-fire on q5 costs one retrieval, and the union is
        # more cautious than either half alone.
        assert "q2" not in union["missed_searches"]

    def test_the_union_is_never_less_cautious_than_either_half(self, report):
        alone = set(report.model.alone["missed_searches"])
        detector_misses = set(report.lane("combined").misses)

        assert set(report.model.union["missed_searches"]) == alone & detector_misses

    def test_reason_codes_are_counted(self, report):
        reasons = report.model.reasons

        assert reasons[REASON_SEARCH_REQUESTED] == 2
        assert reasons["answered_directly"] == 3
        assert sum(reasons.values()) == 5

    def test_the_rendering_names_the_union_and_the_misses(self, report):
        text = report.render()

        assert "Model decision" in text and "union (detector OR model)" in text
        assert "UNION missed (neither half caught): q4" in text
        assert "none retained" in text

    def test_hypothetical_answers_are_reported_as_lengths_only(self, report):
        answers = report.model.as_dict()["hypothetical_answers"]

        assert answers["count"] == 3
        assert answers["chars_total"] == len("A middle value.") + len(
            "It retries."
        ) + len("An institution.")

        serialized = json.dumps(report.as_dict())
        for text in ("A middle value.", "It retries.", "An institution."):
            assert text not in serialized
            assert text not in report.render()

    def test_the_model_is_recorded_per_question_without_its_text(self, report):
        per_question = {row["id"]: row for row in report.model.as_dict()["per_question"]}

        assert per_question["q4"]["route"] == "direct"
        assert per_question["q4"]["detector"] is False
        assert per_question["q4"]["expects_evidence"] is True
        assert "text" not in per_question["q4"] and "answer" not in per_question["q4"]


class FallbacksAreNotTheModelBeingWrongTests:
    def test_a_rate_limited_call_is_an_over_search_and_excluded_from_decided(self, detector):
        # `_script` is called with the request, so fail only the second question.
        def script(user):
            if "second" in user:
                return LLMUnavailable("429", kind=ErrorKind.RATE_LIMIT)
            return ANSWER("fine")

        report = run_curated(
            detector,
            questions(
                q("q1", "first general question", "none"),
                q("q2", "second general question", "none"),
            ),
            decider=model_for(script),
        )
        model = report.model

        assert model.fallbacks == 1
        assert model.reasons[REASON_RATE_LIMITED] == 1
        assert model.alone["over_searches"] == ["q2"]
        assert model.decided == {"judged": 1, "correct": 1, "accuracy": 1.0}
        assert "1 fell back to evidence" in report.render()

    def test_every_case_in_a_run_is_attributed_to_its_own_reason(self, detector):
        script = by_text(
            alpha=ScriptedToolCallingLLM.empty(),
            bravo=ScriptedToolCallingLLM.calling_twice(),
            charlie=CALL(arguments='{"query":"x"}'),
        )
        report = run_curated(
            detector,
            questions(
                q("q1", "alpha", "corpus"),
                q("q2", "bravo", "corpus"),
                q("q3", "charlie", "corpus"),
            ),
            decider=model_for(script),
        )

        reasons = {k: v for k, v in report.model.reasons.items() if v}
        assert reasons == {
            "empty_completion": 1,
            "several_calls": 1,
            REASON_SEARCH_REQUESTED: 1,
        }
        assert report.model.anomalies == {"arguments_supplied": 1}


class StatisticsTests:
    def test_latency_and_tokens_are_summarised(self, detector):
        report = run_curated(
            detector,
            questions(q("q1", "what did the paper find?", "corpus")),
            decider=model_for(lambda user: CALL(input_tokens=40, output_tokens=3)),
        )
        data = report.model.as_dict()

        assert data["tokens"] == {"input": 40, "output": 3}
        assert data["latency_ms"]["p95"] >= 0
        assert data["models"] == []

    def test_an_empty_set_has_no_model_section_rather_than_a_zero_row(self, detector):
        report = run_curated(
            detector,
            parse_question_set(
                {"name": "t", "questions": [{"id": "x", "question": "q", "expected": [
                    {"record": "A", "quote": QUOTE}]}]}
            ),
            decider=model_for(lambda user: CALL()),
        )
        assert report.model is None

    def test_a_raw_and_a_resolved_form_are_sent_together(self, detector):
        llm = ScriptedToolCallingLLM(lambda request: CALL())
        run_curated(
            detector,
            questions(
                q(
                    "q1",
                    "and the second one?",
                    "corpus",
                    resolved_question="What is the sample size of the second study?",
                )
            ),
            decider=ModelEvidenceDecision(llm),
        )
        (request,) = llm.tool_requests

        assert "and the second one?" in request.user
        assert "sample size of the second study" in request.user
