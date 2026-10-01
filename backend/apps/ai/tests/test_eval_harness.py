"""A run, end to end, with the deterministic fakes (IR-133 / IR-394).

Here rather than in `apps/ai/evaluation/tests/` because a run needs the corpus
builder in `corpus.py` and the `space`/`embedder` fixtures next door -- the same
corpus the HTTP-boundary suites drive, so the harness cannot end up measuring a
corpus nobody else tests against.

No vendor account: IR-394's criterion is that a run against the fakes is part of
the normal test suite, and that a real run is a command nobody automates.
"""

import json
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from apps.ai.composition import CompositionRoot
from apps.ai.evaluation import (
    TECHNIQUES,
    RunConfig,
    load_question_set,
    parse_question_set,
    resolve_techniques,
    run,
    run_both,
)
from apps.ai.evaluation.validation import check_question_set
from apps.ai.providers.fakes import ScriptedReranker
from apps.ai.tests.corpus import FLOOD_TEXT, POND_TEXT, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

SYNTHETIC_SET = (
    Path(__file__).resolve().parent.parent / "evaluation" / "fixtures" / "synthetic_set.json"
)

FLOOD_TITLE = "Flood prediction in the Mananga catchment"
POND_TITLE = "Tilapia pond sampling"


@pytest.fixture
def corpus(embedder, space):
    """The two records the committed synthetic set is labelled against."""
    return (
        make_record(title=FLOOD_TITLE, text=FLOOD_TEXT, embedder=embedder, space=space),
        make_record(title=POND_TITLE, text=POND_TEXT, embedder=embedder, space=space),
    )


@pytest.fixture
def reader():
    return make_user("reader@cit.edu")


def _root(embedder, permits=None):
    """A root with fake vendors and no LLM -- a retrieval measurement must not
    need a configured model."""
    return CompositionRoot(
        embedder=embedder,
        reranker=ScriptedReranker(),
        permits=permits or (lambda record: True),
    )


def _one_question(record_title, quote, question="what did they do?"):
    return parse_question_set(
        {
            "name": "inline",
            "questions": [
                {
                    "id": "q1",
                    "question": question,
                    "expected": [{"record": record_title, "quote": quote}],
                }
            ],
        }
    )


# -- the committed synthetic set ----------------------------------------------


def test_the_committed_synthetic_set_scores_full_recall(corpus, reader, embedder):
    question_set = load_question_set(SYNTHETIC_SET)
    report = run(
        _root(embedder), question_set, RunConfig(), user=reader
    )
    assert report.retrieval_recall == 1.0
    assert report.final_set_recall == 1.0
    assert report.micro_retrieval_recall == 1.0


def test_every_label_in_the_committed_set_resolves_against_the_corpus(corpus):
    checks = check_question_set(load_question_set(SYNTHETIC_SET))
    assert [c.problem for c in checks if not c.ok] == []


# -- the measures ------------------------------------------------------------


def test_a_quote_no_record_contains_scores_zero_and_is_named(corpus, reader, embedder):
    question_set = _one_question(FLOOD_TITLE, "groundwater salinity in coastal wells")
    report = run(_root(embedder), question_set, RunConfig(), user=reader)
    assert report.retrieval_recall == 0.0
    assert report.outcomes[0].missed == ("groundwater salinity in coastal wells",)


def test_the_right_quote_under_the_wrong_record_scores_zero(corpus, reader, embedder):
    question_set = _one_question(POND_TITLE, "rainfall gauge data to predict flooding")
    report = run(_root(embedder), question_set, RunConfig(), user=reader)
    assert report.retrieval_recall == 0.0


def test_the_two_measures_are_not_the_same_number(corpus, reader, embedder):
    """IR-394's reason for the second measure: a passage retrieval found can be
    discarded before the model sees it, and retrieval recall cannot see that."""
    question_set = load_question_set(SYNTHETIC_SET)
    report = run(
        _root(embedder),
        question_set,
        RunConfig(max_sources=0),
        user=reader,
    )
    assert report.retrieval_recall == 1.0
    assert report.final_set_recall == 0.0


def test_the_disclosure_gate_shows_up_in_the_final_set_measure(corpus, reader, embedder):
    """A gate refusing every record is the shipped configuration today (IR-250),
    and it must be visible as a final-set number rather than as a silent zero."""
    report = run(
        _root(embedder, permits=lambda record: False),
        load_question_set(SYNTHETIC_SET),
        RunConfig(),
        user=reader,
    )
    assert report.retrieval_recall == 1.0
    assert report.final_set_recall == 0.0


def test_k_bounds_the_retrieval_measure(corpus, reader, embedder):
    """recall@1 over a two-record corpus cannot exceed what one passage can
    hold, so a question expecting both passages scores a half."""
    question_set = parse_question_set(
        {
            "name": "inline",
            "questions": [
                {
                    "id": "q1",
                    "question": "rainfall flooding and tilapia ponds",
                    "expected": [
                        {"record": FLOOD_TITLE, "quote": "rainfall gauge data to predict flooding"},
                        {"record": POND_TITLE, "quote": "tilapia ponds stocked in brackish water"},
                    ],
                }
            ],
        }
    )
    report = run(
        _root(embedder), question_set, RunConfig(retrieval_limit=1, max_sources=1), user=reader
    )
    assert report.retrieval_recall == 0.5


def test_a_run_reads_no_more_than_k_passages_for_the_first_measure(corpus, reader, embedder):
    report = run(
        _root(embedder), load_question_set(SYNTHETIC_SET), RunConfig(retrieval_limit=1), user=reader
    )
    assert all(o.retrieved_count <= 1 for o in report.outcomes)


# -- the comparison IR-133 asks for -------------------------------------------


def test_both_configurations_run_and_are_labelled_for_comparison(corpus, reader, embedder):
    reports = run_both(_root(embedder), load_question_set(SYNTHETIC_SET), user=reader)
    assert [r.config.label for r in reports] == ["no-reranking", "with-reranking"]
    assert reports[0].provenance["reranker"] == "NoOpReranker"
    assert reports[1].provenance["reranker"] == "ScriptedReranker"


def test_switching_reranking_off_leaves_the_disclosure_gate_in_place(corpus, reader, embedder):
    """`without_reranking` swaps in a no-op rather than removing the decorator
    the gate lives inside, so a comparison changes one thing."""
    root = _root(embedder, permits=lambda record: False)
    report = run(root, load_question_set(SYNTHETIC_SET), RunConfig(reranking=False), user=reader)
    assert report.final_set_recall == 0.0


def test_provenance_records_enough_to_repeat_the_run(corpus, reader, embedder):
    report = run(_root(embedder), load_question_set(SYNTHETIC_SET), RunConfig(), user=reader)
    assert report.provenance["embedding_spaces"]
    assert report.provenance["retrieval_modes"] == ["vector"]
    assert "ran_at" in report.provenance
    assert report.as_dict()["config"]["label"] == "with-reranking"
    assert report.as_dict()["measures"]["recall@10"] == 1.0


# -- the command --------------------------------------------------------------


def test_dry_run_passes_when_every_label_resolves(corpus, capsys):
    call_command("eval_retrieval", questions=str(SYNTHETIC_SET), dry_run=True)
    assert "Every label resolves" in capsys.readouterr().out


def test_dry_run_refuses_a_quote_that_is_in_no_chunk(corpus, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "name": "bad",
                "questions": [
                    {
                        "id": "q1",
                        "question": "what did they do?",
                        "expected": [
                            {"record": FLOOD_TITLE, "quote": "a sentence no paper contains"}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CommandError, match="do not resolve"):
        call_command("eval_retrieval", questions=str(bad), dry_run=True)


def test_the_command_refuses_to_run_without_a_user(corpus):
    with pytest.raises(CommandError, match="--user is required"):
        call_command("eval_retrieval", questions=str(SYNTHETIC_SET))


# -- the technique configuration (ADR-033 §5) --------------------------------


def test_a_run_records_every_technique_even_the_unbuilt_ones(corpus, reader, embedder):
    """A results file that omits a switch cannot be compared with a later one."""
    config = RunConfig(techniques=resolve_techniques())
    report = run(_root(embedder), load_question_set(SYNTHETIC_SET), config, user=reader)

    recorded = report.as_dict()["config"]["techniques"]
    assert set(recorded) == {t.name for t in TECHNIQUES}
    assert recorded["fusion"]["ticket"] == "IR-395"
    assert report.provenance["techniques_moved"] == []


def test_the_command_records_the_technique_configuration_in_the_results_file(
    corpus, reader, embedder, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "apps.ai.management.commands.eval_retrieval.composition_root",
        lambda: _root(embedder),
    )
    call_command(
        "eval_retrieval",
        questions=str(SYNTHETIC_SET),
        user=reader.email,
        reranking="on",
        out=str(tmp_path),
    )

    written = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert set(written["runs"][0]["config"]["techniques"]) == {
        t.name for t in TECHNIQUES
    }


def test_the_command_refuses_a_technique_that_is_not_built_yet(corpus, reader):
    """Measuring the baseline under a results file claiming otherwise is the
    one failure the registry exists to prevent.

    Named on `relevance_cut_off` rather than `fusion`: this test was written
    against fusion while nothing implemented it, and IR-395 landed
    `AI_RETRIEVAL_FUSION_ENABLED`, so fusion is now a technique the harness
    can really run. The property is about an *unbuilt* technique, so it moved
    to one that still is (IR-396) rather than being deleted.
    """
    with pytest.raises(CommandError, match="IR-396"):
        call_command(
            "eval_retrieval",
            questions=str(SYNTHETIC_SET),
            user=reader.email,
            techniques=["relevance_cut_off=0.3"],
        )


def test_listing_the_techniques_needs_no_question_set_and_no_user(capsys):
    call_command("eval_retrieval", list_techniques=True)

    out = capsys.readouterr().out
    assert "AI_RETRIEVAL_FUSION_ENABLED" in out
    assert "not built yet" in out


def test_the_results_file_pins_the_question_set_by_content_not_only_by_path(
    corpus, reader, embedder, tmp_path, monkeypatch
):
    """A re-labelled set at the same path must not reproduce as the same run."""
    monkeypatch.setattr(
        "apps.ai.management.commands.eval_retrieval.composition_root",
        lambda: _root(embedder),
    )
    call_command(
        "eval_retrieval",
        questions=str(SYNTHETIC_SET),
        user=reader.email,
        reranking="on",
        out=str(tmp_path),
    )

    written = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    digest = written["runs"][0]["provenance"]["question_set_sha256"]
    assert len(digest) == 64
    assert digest != "0" * 64
