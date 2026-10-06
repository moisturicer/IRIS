"""The committed proxy set carries the IR-463 categories, each labelled by kind."""

from pathlib import Path

from apps.ai.evaluation.labels import load_question_set

PROXY = Path(__file__).resolve().parents[5] / "docs" / "evaluation" / "proxy_starter.json"


def test_the_committed_proxy_set_carries_every_new_category_labelled_by_kind():
    question_set = load_question_set(PROXY)
    assert all(q.kind for q in question_set.questions)
    assert {
        "mechanism",
        "exact-term",
        "cross-paper",
        "near-duplicate",
        "general-knowledge",
        "off-corpus-research",
        "ambiguous",
        "follow-up-after-direct",
        "follow-up-after-grounded",
    } <= {q.kind for q in question_set.questions}


def test_general_knowledge_questions_are_answered_not_refused():
    general = [q for q in load_question_set(PROXY).questions if q.kind == "general-knowledge"]
    assert general
    assert all(
        q.evidence_required == "none"
        and q.expected_outcome == "answer"
        and not q.expects_decline
        for q in general
    )


def test_the_set_still_scores_only_the_questions_that_have_passages():
    question_set = load_question_set(PROXY)
    assert 0 < len(question_set.scored) < len(question_set)
    assert all(q.expected for q in question_set.scored)
