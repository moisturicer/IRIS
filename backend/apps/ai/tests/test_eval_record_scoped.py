"""Retrieval inside one paper, measured as Paper Chat retrieves (IR-1052)."""

import json

import pytest
from django.core.management import call_command

from apps.ai.composition import CompositionRoot
from apps.ai.evaluation import QuestionSetError, RunConfig, parse_question_set, run
from apps.ai.providers.fakes import ScriptedReranker
from apps.ai.tests.corpus import FLOOD_TEXT, POND_TEXT, make_record, make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

FLOOD_TITLE = "Flood prediction in the Mananga catchment"
POND_TITLE = "Tilapia pond sampling"
POND_QUOTE = "tilapia ponds stocked in brackish water"
FLOOD_QUESTION = "rainfall gauge data to predict flooding"


@pytest.fixture
def corpus(embedder, space):
    return (
        make_record(title=FLOOD_TITLE, text=FLOOD_TEXT, embedder=embedder, space=space),
        make_record(title=POND_TITLE, text=POND_TEXT, embedder=embedder, space=space),
    )


@pytest.fixture
def reader():
    return make_user("reader@cit.edu")


def _root(embedder):
    return CompositionRoot(
        embedder=embedder, reranker=ScriptedReranker(), permits=lambda record: True
    )


def _pond_question(qid="in-paper", scope=POND_TITLE):
    """A flood-worded question whose label is in the pond paper: only a
    retriever narrowed to that paper can put the pond passage first."""
    question = {
        "id": qid,
        "question": FLOOD_QUESTION,
        "expected": [{"record": POND_TITLE, "quote": POND_QUOTE}],
    }
    if scope is not None:
        question["scope_record"] = scope
    return question


def _set(*questions):
    return parse_question_set({"name": "inline", "questions": list(questions)})


def test_a_scoped_question_retrieves_only_inside_its_record(corpus, reader, embedder):
    config = RunConfig(retrieval_limit=1, max_sources=1)
    scoped = run(_root(embedder), _set(_pond_question()), config, user=reader)
    unscoped = run(
        _root(embedder), _set(_pond_question(scope=None)), config, user=reader
    )

    assert scoped.retrieval_recall == 1.0
    assert unscoped.retrieval_recall == 0.0
    assert scoped.outcomes[0].scope_record == POND_TITLE


def test_a_scope_naming_a_record_by_id_is_honoured(corpus, reader, embedder):
    pond = corpus[1]
    question = {
        "id": "by-id",
        "question": FLOOD_QUESTION,
        "scope_record": pond.pk,
        "expected": [{"record": pond.pk, "quote": POND_QUOTE}],
    }
    report = run(
        _root(embedder), _set(question), RunConfig(retrieval_limit=1), user=reader
    )
    assert report.retrieval_recall == 1.0


def test_a_scope_title_with_stray_whitespace_still_resolves(corpus, reader, embedder):
    loose = "  Tilapia   pond   sampling "
    question = {
        "id": "loose",
        "question": FLOOD_QUESTION,
        "scope_record": loose,
        "expected": [{"record": loose, "quote": POND_QUOTE}],
    }
    report = run(
        _root(embedder), _set(question), RunConfig(retrieval_limit=1), user=reader
    )
    assert report.retrieval_recall == 1.0


def test_the_slice_reports_its_own_denominator_beside_the_corpus(
    corpus, reader, embedder
):
    corpus_question = {
        "id": "corpus",
        "question": FLOOD_QUESTION,
        "expected": [{"record": FLOOD_TITLE, "quote": FLOOD_QUESTION}],
    }
    report = run(
        _root(embedder),
        _set(corpus_question, _pond_question()),
        RunConfig(retrieval_limit=1, max_sources=1),
        user=reader,
    )

    slices = report.as_dict()["slices"]
    assert slices["corpus"]["questions"] == 1
    assert slices["record_scoped"]["questions"] == 1
    assert slices["record_scoped"]["recall@1"] == 1.0
    assert slices["record_scoped"]["in_paper_minus_corpus_recall@1"] == 0.0
    assert "record-scoped" in report.render()


def test_a_set_with_no_scoped_question_reports_no_slice(corpus, reader, embedder):
    report = run(
        _root(embedder), _set(_pond_question(scope=None)), RunConfig(), user=reader
    )
    assert report.as_dict()["slices"]["record_scoped"] is None


def test_a_scope_naming_no_record_stops_the_run_before_any_retrieval(
    corpus, reader, embedder
):
    question = {**_pond_question(scope="No such paper")}
    question["expected"] = [{"record": "No such paper", "quote": POND_QUOTE}]
    with pytest.raises(QuestionSetError, match="No such paper"):
        run(_root(embedder), _set(question), RunConfig(), user=reader)


def test_the_results_file_carries_the_slice(
    corpus, reader, embedder, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "apps.ai.management.commands.eval_retrieval.composition_root",
        lambda: _root(embedder),
    )
    path = tmp_path / "scoped.json"
    path.write_text(
        json.dumps({"name": "scoped", "questions": [_pond_question()]}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "runs"

    call_command(
        "eval_retrieval", questions=str(path), user=reader.email, out=str(out_dir)
    )

    written = json.loads(next(out_dir.glob("*.json")).read_text(encoding="utf-8"))
    for run_data in written["runs"]:
        assert run_data["slices"]["record_scoped"]["questions"] == 1
        assert run_data["questions"][0]["scope_record"] == POND_TITLE
