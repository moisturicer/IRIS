"""A question that carries no expected passage, in a run (IR-463).

Its own file so it can reuse `test_eval_harness`'s corpus fixtures without
editing that module.
"""

import json

import pytest

from apps.ai.evaluation import RunConfig, parse_question_set, run
from apps.ai.evaluation.validation import check_question_set
from apps.ai.tests.test_eval_harness import (  # noqa: F401  (fixtures)
    SYNTHETIC_SET,
    _root,
    corpus,
    reader,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


def _with_general_knowledge():
    data = json.loads(SYNTHETIC_SET.read_text(encoding="utf-8"))
    data["questions"].append(
        {
            "id": "gk",
            "question": "what is the difference between a mean and a median?",
            "evidence_required": "none",
            "expected_outcome": "answer",
            "expected": [],
        }
    )
    return parse_question_set(data)


def test_a_question_with_no_passages_does_not_move_recall(corpus, reader, embedder):  # noqa: F811
    report = run(_root(embedder), _with_general_knowledge(), RunConfig(), user=reader)
    assert report.retrieval_recall == 1.0
    assert "gk" not in [o.question_id for o in report.outcomes]
    assert report.question_set.as_dict()["without_passages"] == 1


def test_dry_run_checks_a_set_holding_a_question_with_no_passages(corpus):  # noqa: F811
    assert [c.problem for c in check_question_set(_with_general_knowledge()) if not c.ok] == []
