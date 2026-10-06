"""Retrieval evaluation: recall@10 over a labelled question set (IR-133).

ADR-023 is the decision this package implements, as amended by IR-391: two
tiers never conflated, labels that survive re-chunking, two measures per run,
one change at a time, and a manual command rather than CI.

`labels` is the question-set format, `harness` is a run, `report` is what a run
produces, `techniques` is ADR-033 §5's switches a run can move,
`validation` is the pre-flight a labeller uses, and `evidence` is IR-464's
curated instrument for the evidence detector. Only `validation` touches the
database outside a run.
"""

from .evidence import (
    EvidenceReport,
    Judgement,
    annotated,
    judge,
    run_curated,
)
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
from .techniques import (
    TECHNIQUES,
    ResolvedTechniques,
    Technique,
    TechniqueError,
    parse_override,
    render_registry,
)
from .techniques import resolve as resolve_techniques
from .validation import check_question_set, render_checks

__all__ = [
    "EvalReport",
    "EvidenceReport",
    "Judgement",
    "TECHNIQUES",
    "ResolvedTechniques",
    "Technique",
    "TechniqueError",
    "Label",
    "Question",
    "QuestionOutcome",
    "QuestionSet",
    "QuestionSetError",
    "RunConfig",
    "annotated",
    "check_question_set",
    "compare",
    "load_question_set",
    "normalize",
    "parse_question_set",
    "parse_override",
    "render_checks",
    "render_registry",
    "resolve_techniques",
    "judge",
    "run",
    "run_both",
    "run_curated",
]
