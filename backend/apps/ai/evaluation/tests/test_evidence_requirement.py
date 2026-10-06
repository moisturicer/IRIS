"""What a question needs from the corpus, and what the right outcome is (IR-463).

Pure, like `test_labels.py`: no database, no vendor, no model. The schema is two
fields because an empty expected-passage list cannot carry two meanings -- a
general-knowledge question has no passages and must be *answered*.
"""

import pytest

from apps.ai.evaluation.labels import QuestionSetError, parse_question_set

QUOTE = "the document stopped moving and nobody noticed that it had"
GROUNDED = {"expected": [{"record": "A", "quote": QUOTE}]}


def _q(**fields):
    return {"name": "t", "questions": [{"id": "q1", "question": "what?", **fields}]}


def test_the_loader_reads_kind_and_the_three_evidence_fields():
    question = parse_question_set(
        _q(
            kind="mechanism",
            evidence_required="corpus",
            expected_outcome="answer",
            institutional=False,
            **GROUNDED,
        )
    ).questions[0]
    assert question.kind == "mechanism"
    assert question.evidence_required == "corpus"
    assert question.expected_outcome == "answer"
    assert question.institutional is False


def test_a_question_without_the_new_fields_still_loads_unchanged():
    question = parse_question_set(_q(**GROUNDED)).questions[0]
    assert (question.kind, question.evidence_required) == (None, None)
    assert (question.expected_outcome, question.institutional) == (None, None)
    assert question.deliberately_empty is False


@pytest.mark.parametrize(
    "fields, match",
    [
        ({"evidence_required": "some", "expected_outcome": "answer", **GROUNDED}, "evidence_required"),
        ({"evidence_required": "none", "expected_outcome": "refuse", "expected": []}, "expected_outcome"),
        (
            {"evidence_required": "corpus", "expected_outcome": "answer", "institutional": "yes", **GROUNDED},
            "institutional",
        ),
        ({"kind": 3, **GROUNDED}, "kind"),
        ({"evidence_required": "corpus", **GROUNDED}, "together"),
        ({"expected_outcome": "answer", **GROUNDED}, "together"),
    ],
)
def test_an_invalid_or_half_declared_field_is_refused(fields, match):
    with pytest.raises(QuestionSetError, match=match):
        parse_question_set(_q(**fields))


def test_a_general_knowledge_question_loads_and_is_not_a_refusal():
    question = parse_question_set(
        _q(evidence_required="none", expected_outcome="answer", expected=[])
    ).questions[0]
    assert question.deliberately_empty
    assert question.expected == ()
    assert question.expected_outcome == "answer"
    assert not question.expects_decline


@pytest.mark.parametrize("outcome", ["decline-no-evidence", "decline-restricted"])
def test_the_decline_outcomes_are_declines(outcome):
    question = parse_question_set(
        _q(evidence_required="corpus", expected_outcome=outcome, expected=[])
    ).questions[0]
    assert question.expects_decline


def test_a_clarify_outcome_is_neither_an_answer_nor_a_decline():
    question = parse_question_set(
        _q(evidence_required="none", expected_outcome="clarify", expected=[])
    ).questions[0]
    assert not question.expects_decline


def test_an_empty_expected_set_without_a_declaration_is_still_unlabelled():
    with pytest.raises(QuestionSetError, match="at least one expected"):
        parse_question_set(_q(expected=[]))


def test_drop_incomplete_skips_the_unlabelled_and_never_the_deliberately_empty():
    question_set = parse_question_set(
        {
            "name": "t",
            "questions": [
                {"id": "grounded", "question": "a?", **GROUNDED},
                {"id": "unlabelled", "question": "b?", "expected": []},
                {
                    "id": "general",
                    "question": "c?",
                    "evidence_required": "none",
                    "expected_outcome": "answer",
                    "expected": [],
                },
            ],
        },
        drop_incomplete=True,
    )
    assert [q.id for q in question_set.questions] == ["grounded", "general"]
    assert question_set.skipped == ("unlabelled",)


@pytest.mark.parametrize(
    "fields, match",
    [
        ({"evidence_required": "none", "expected_outcome": "answer", **GROUNDED}, "needs no evidence"),
        ({"evidence_required": "corpus", "expected_outcome": "decline-no-evidence", **GROUNDED}, "declines"),
        ({"evidence_required": "corpus", "expected_outcome": "answer", "expected": []}, "needs at least one"),
    ],
)
def test_a_self_contradictory_declaration_is_refused(fields, match):
    with pytest.raises(QuestionSetError, match=match):
        parse_question_set(_q(**fields))


def test_the_set_separates_scored_questions_from_those_with_no_passages():
    question_set = parse_question_set(
        {
            "name": "t",
            "questions": [
                {"id": "a", "question": "a?", **GROUNDED},
                {
                    "id": "b",
                    "question": "b?",
                    "evidence_required": "none",
                    "expected_outcome": "answer",
                    "expected": [],
                },
            ],
        }
    )
    assert [q.id for q in question_set.scored] == ["a"]
    assert question_set.as_dict()["without_passages"] == 1


def test_the_retrieval_harness_imports_no_model_path():
    """The harness calls no model, so a run spends no generation credit and
    works where none is configured. Asserted on the source, as the no-gateway
    test is."""
    from pathlib import Path

    import apps.ai.evaluation as package

    forbidden = ("inference", "openai_compatible", "llm_for", "answer_service", "AI_GATEWAY")
    for path in Path(package.__file__).parent.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for name in forbidden:
            assert name not in source, f"{path.name} reaches a model via {name!r}"
