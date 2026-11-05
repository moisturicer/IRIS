"""The correct-refusal measure and the false-refusal guard (IR-454).

No database and no vendor: a report is a value built from outcomes, so the two
new numbers are testable with outcomes typed out by hand. The end-to-end half,
through a real `run`, is in `apps/ai/tests/test_eval_harness.py`.

Why this exists: both recall measures can only go down when a precision
technique (ADR-033 §3's relevance cut-off, §4's cap and budget) removes a
passage. Without a question the corpus cannot answer, a run can show what a
floor costs and never what it buys.
"""

from apps.ai.evaluation.labels import parse_question_set
from apps.ai.evaluation.report import EvalReport, QuestionOutcome, RunConfig, compare

SET = parse_question_set(
    {
        "name": "inline",
        "questions": [
            {
                "id": "answerable",
                "question": "how were the fish ponds sampled?",
                "evidence_required": "corpus",
                "expected_outcome": "answer",
                "expected": [
                    {"record": "Ponds", "quote": "tilapia ponds stocked in brackish water"}
                ],
            },
            {
                "id": "off-corpus",
                "question": "what did the 2021 fasting trial conclude?",
                "evidence_required": "corpus",
                "expected_outcome": "decline-no-evidence",
                "expected": [],
            },
            {
                "id": "general",
                "question": "what is a p-value?",
                "evidence_required": "none",
                "expected_outcome": "answer",
                "expected": [],
            },
            {
                "id": "restricted",
                "question": "what did the embargoed thesis find?",
                "evidence_required": "corpus",
                "expected_outcome": "decline-restricted",
                "expected": [],
            },
        ],
    }
)


def _answerable(qid, *, final, expected=1, hits=None):
    found = expected if hits is None else hits
    return QuestionOutcome(
        question_id=qid,
        question="?",
        expected=expected,
        retrieved_hits=found,
        final_hits=found if final else 0,
        retrieved_count=10,
        final_count=final,
    )


def _unanswerable(qid, *, final):
    return QuestionOutcome(
        question_id=qid,
        question="?",
        expected=0,
        retrieved_hits=0,
        final_hits=0,
        retrieved_count=final,
        final_count=final,
        expects_refusal=True,
    )


def _report(outcomes=(), refusals=(), config=None):
    return EvalReport(
        question_set=SET,
        config=config or RunConfig(),
        outcomes=tuple(outcomes),
        refusals=tuple(refusals),
    )


# -- which questions are unanswerable ----------------------------------------


def test_only_a_corpus_question_that_should_be_declined_for_want_of_evidence_is_unanswerable():
    """A general-knowledge question also has no passages, and must be answered;
    a restricted one is a visibility question, not a corpus gap (IR-463)."""
    assert [q.id for q in SET.unanswerable] == ["off-corpus"]


def test_the_question_set_reports_how_many_unanswerable_questions_it_holds():
    assert SET.as_dict()["unanswerable"] == 1


# -- the correct-refusal measure ----------------------------------------------


def test_correct_refusal_is_the_share_of_unanswerable_questions_given_no_passage():
    report = _report(
        refusals=[
            _unanswerable("a", final=0),
            _unanswerable("b", final=0),
            _unanswerable("c", final=3),
            _unanswerable("d", final=8),
        ]
    )
    assert report.correct_refusal == 0.5


def test_correct_refusal_is_absent_not_zero_when_the_set_has_no_unanswerable_question():
    """A 0.0 would read as "refused nothing", which no run measured."""
    report = _report(outcomes=[_answerable("q1", final=4)])
    assert report.correct_refusal is None
    assert report.as_dict()["measures"]["correct_refusal"] is None


def test_unanswerable_questions_given_passages_are_named():
    report = _report(
        refusals=[_unanswerable("refused", final=0), _unanswerable("leaked", final=2)]
    )
    assert report.unanswered_refusals == ("leaked",)


# -- never blended -------------------------------------------------------------


def test_the_refusal_measure_moves_neither_recall_measure():
    """ADR-027 §2: two signals are never combined into one score."""
    recall_only = _report(outcomes=[_answerable("q1", final=4)])
    with_refusals = _report(
        outcomes=[_answerable("q1", final=4)],
        refusals=[_unanswerable("u1", final=0), _unanswerable("u2", final=5)],
    )
    for measure in (
        "retrieval_recall",
        "final_set_recall",
        "micro_retrieval_recall",
        "micro_final_set_recall",
    ):
        assert getattr(with_refusals, measure) == getattr(recall_only, measure) == 1.0


def test_the_results_file_carries_recall_and_refusal_as_separate_measures():
    measures = _report(
        outcomes=[_answerable("q1", final=4)],
        refusals=[_unanswerable("u1", final=0)],
    ).as_dict()["measures"]
    assert measures["recall@10"] == 1.0
    assert measures["final_set_recall"] == 1.0
    assert measures["correct_refusal"] == 1.0
    assert measures["unanswerable_questions"] == 1


def test_the_results_file_keeps_each_unanswerable_question_apart_from_the_scored_ones():
    data = _report(
        outcomes=[_answerable("q1", final=4)],
        refusals=[_unanswerable("u1", final=0)],
    ).as_dict()
    assert [q["question_id"] for q in data["questions"]] == ["q1"]
    assert [q["question_id"] for q in data["refusals"]] == ["u1"]
    assert data["refusals"][0]["refused"] is True


# -- the false-refusal guard ---------------------------------------------------


def test_an_answerable_question_given_no_passage_is_a_false_refusal_named_by_id():
    report = _report(
        outcomes=[
            _answerable("kept", final=4),
            _answerable("dropped", final=0),
            _answerable("also-dropped", final=0, hits=0),
        ]
    )
    assert report.false_refusals == ("dropped", "also-dropped")
    assert report.as_dict()["measures"]["false_refusals"] == ["dropped", "also-dropped"]


def test_a_question_given_passages_that_miss_its_label_is_a_miss_not_a_false_refusal():
    """Recall already counts that one. A false refusal is the reader-invisible
    case: the model was given nothing at all (ADR-033 §Risk)."""
    report = _report(outcomes=[_answerable("wrong-passages", final=6, hits=0)])
    assert report.false_refusals == ()


def test_the_rendered_report_names_every_false_refusal_and_the_refusal_measure():
    text = _report(
        outcomes=[_answerable("q07", final=0), _answerable("q08", final=3)],
        refusals=[_unanswerable("q55", final=0), _unanswerable("q56", final=4)],
    ).render()
    assert "correct refusal" in text
    assert "0.500" in text
    assert "q07" in text
    assert "q56" in text


# -- one run, both numbers -----------------------------------------------------


def test_the_comparison_shows_recall_and_refusal_side_by_side_per_configuration():
    """A floor that refuses every off-corpus question and also drops answerable
    passages is a bad floor; only both numbers from one configuration show it."""
    baseline = _report(
        outcomes=[_answerable("q1", final=4), _answerable("q2", final=4)],
        refusals=[_unanswerable("u1", final=6)],
        config=RunConfig(reranking=False),
    )
    floor = _report(
        outcomes=[_answerable("q1", final=4), _answerable("q2", final=0)],
        refusals=[_unanswerable("u1", final=0)],
        config=RunConfig(reranking=True),
    )
    table = compare([baseline, floor])
    assert "refusal" in table
    assert "false-ref" in table
    row = next(line for line in table.splitlines() if line.startswith("with-reranking"))
    assert "1.000" in row  # correct refusal on the floor
    assert row.rstrip().endswith("1")  # one false refusal


def test_the_comparison_marks_refusal_unmeasured_rather_than_zero():
    table = compare([_report(outcomes=[_answerable("q1", final=4)])])
    row = next(line for line in table.splitlines() if line.startswith("with-reranking"))
    assert "n/a" in row
