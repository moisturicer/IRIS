"""Retrieval evaluation: recall@10 over a labelled question set (IR-133).

ADR-023 is the decision this package implements, as amended by IR-391: two
tiers never conflated, labels that survive re-chunking, two measures per run,
one change at a time, and a manual command rather than CI.

`labels` is the question-set format, `harness` is a run, `report` is what a run
produces, `validation` is the pre-flight a labeller uses. Only `validation`
touches the database outside a run.
"""

from .harness import run, run_both
from .labels import (
    Label,
    Question,
    QuestionSet,
    QuestionSetError,
    load_question_set,
    normalize,
    parse_question_set,
)
from .report import EvalReport, QuestionOutcome, RunConfig, compare
from .validation import check_question_set, render_checks

__all__ = [
    "EvalReport",
    "Label",
    "Question",
    "QuestionOutcome",
    "QuestionSet",
    "QuestionSetError",
    "RunConfig",
    "check_question_set",
    "compare",
    "load_question_set",
    "normalize",
    "parse_question_set",
    "render_checks",
    "run",
    "run_both",
]
