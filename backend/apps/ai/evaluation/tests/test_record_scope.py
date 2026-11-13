"""A question scoped to one Record, as Paper Chat asks it (IR-1052)."""

import pytest

from apps.ai.evaluation.labels import QuestionSetError, parse_question_set

QUOTE = "rainfall gauge data to predict flooding"


def _set(*questions):
    return parse_question_set({"name": "inline", "questions": list(questions)})


def _q(qid="q1", scope="Flood paper", record="Flood paper", **extra):
    return {
        "id": qid,
        "question": "what data did they use?",
        "scope_record": scope,
        "expected": [{"record": record, "quote": QUOTE}],
        **extra,
    }


def test_a_scoped_question_carries_its_record_and_counts_in_the_slice():
    question_set = _set(_q(), {**_q("q2"), "scope_record": None})
    assert question_set.questions[0].scope_record == "Flood paper"
    assert question_set.questions[1].scope_record is None
    assert [q.id for q in question_set.record_scoped] == ["q1"]
    assert question_set.as_dict()["record_scoped"] == 1


def test_a_scope_matches_its_labels_by_normalized_title():
    question_set = _set(_q(scope="  FLOOD   paper "))
    assert question_set.questions[0].scope_record == "FLOOD   paper"


def test_a_label_outside_the_scoped_record_is_refused():
    with pytest.raises(QuestionSetError, match="outside its scope"):
        _set(_q(record="Pond paper"))


def test_an_id_scope_needs_id_labels():
    assert _set(_q(scope=7, record=7)).questions[0].scope_record == 7
    with pytest.raises(QuestionSetError, match="outside its scope"):
        _set(_q(scope=7, record="Flood paper"))


@pytest.mark.parametrize("bad", ["", "   ", "TODO", 1.5, ["x"], True])
def test_a_blank_or_malformed_scope_is_refused(bad):
    with pytest.raises(QuestionSetError, match="scope_record"):
        _set(_q(scope=bad))
