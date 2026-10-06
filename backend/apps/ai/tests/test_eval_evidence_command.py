"""`eval_evidence` measures and records nothing else (IR-464, ADR-035 §10).

The curated instrument creates no `Conversation`, no `Turn` and no shadow row,
and calls no model — the properties that keep it a different instrument from
IR-466's shadow pilot. Written in the spirit of
`test_one_retrieval_stack.py` and the no-gateway test: it fails if that stops
being true.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.ai.models import Conversation, Turn

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

QUOTE = "the document stopped moving and nobody noticed that it had"


def write_set(tmp_path, *questions, name="curated-test"):
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps({"name": name, "tier": "proxy", "questions": list(questions)}),
        encoding="utf-8",
    )
    return str(path)


def grounded(qid, text, **extra):
    return {
        "id": qid,
        "question": text,
        "evidence_required": "corpus",
        "expected_outcome": "answer",
        "expected": [{"record": "A", "quote": QUOTE}],
        **extra,
    }


def direct(qid, text, **extra):
    return {
        "id": qid,
        "question": text,
        "evidence_required": "none",
        "expected_outcome": "answer",
        "expected": [],
        **extra,
    }


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_command_creates_no_conversation_and_no_turn(tmp_path, capsys):
    questions = write_set(
        tmp_path,
        grounded("q1", "what did the paper find?", kind="mechanism"),
        direct("q2", "what is a median?", kind="general-knowledge"),
    )
    before = (Conversation.objects.count(), Turn.objects.count())

    call_command("eval_evidence", "--questions", questions, "--no-write")

    assert (Conversation.objects.count(), Turn.objects.count()) == before
    assert before == (0, 0)
    assert "Detector" in capsys.readouterr().out


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_command_calls_no_model(tmp_path, monkeypatch):
    """No vendor call and no provider construction: a run costs nothing, which
    is what lets it run on any checkout."""
    import apps.ai.composition as composition

    def explode(*args, **kwargs):
        raise AssertionError(
            "eval_evidence built a composition root — it must call no model "
            "(IR-464 acceptance criteria)"
        )

    monkeypatch.setattr(composition, "composition_root", explode)
    call_command(
        "eval_evidence",
        "--questions",
        write_set(tmp_path, grounded("q1", "what did the paper find?")),
        "--no-write",
    )


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_the_results_file_carries_the_rule_set_digest_and_an_empty_model_slot(
    tmp_path,
):
    out = tmp_path / "runs"
    call_command(
        "eval_evidence",
        "--questions",
        write_set(tmp_path, grounded("q1", "what did the paper find?")),
        "--out",
        str(out),
    )
    written = list(out.glob("*-evidence-*.json"))
    assert len(written) == 1

    data = json.loads(written[0].read_text(encoding="utf-8"))
    assert data["instrument"] == "curated"
    assert len(data["rule_set_digest"]) == 64
    assert data["provenance"]["rule_set_digest"] == data["rule_set_digest"]
    assert data["provenance"]["question_set_sha256"] != "unknown"
    assert data["provenance"]["AI_EVIDENCE_DECISION"] == "off"
    assert data["model"] is None
    assert data["provenance"]["model"] is None
    assert data["rule_set"]["definition"]["codes"]


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_an_unannotated_set_is_refused_rather_than_scored_as_zero(tmp_path):
    questions = write_set(
        tmp_path,
        {"id": "q1", "question": "x", "expected": [{"record": "A", "quote": QUOTE}]},
    )
    with pytest.raises(CommandError, match="evidence_required"):
        call_command("eval_evidence", "--questions", questions, "--no-write")


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_a_thin_category_is_named_as_inconclusive(tmp_path, capsys):
    call_command(
        "eval_evidence",
        "--questions",
        write_set(tmp_path, grounded("q1", "what did the paper find?", kind="thin")),
        "--no-write",
    )
    out = capsys.readouterr().out
    assert "INCONCLUSIVE" in out
    assert "thin" in out


@override_settings(AI_EVIDENCE_INSTITUTION_TERMS=("CIT-U",))
def test_a_combined_miss_is_reported_without_becoming_a_refusal(tmp_path, capsys):
    """A high-recall rule may add retrieval; a detector miss may never become
    a refusal. The command says the model decision is what covers it."""
    call_command(
        "eval_evidence",
        "--questions",
        write_set(tmp_path, grounded("q1", "what exactly did they say?")),
        "--no-write",
    )
    out = capsys.readouterr().out
    assert "raised no reason code" in out
    assert "defense in depth, not a classifier" in out
