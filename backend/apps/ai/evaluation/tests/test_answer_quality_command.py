"""IR-956: the committed set and the command's free steps. No database, no vendor."""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from apps.ai.evaluation import answer_quality as aq

SET = Path(__file__).resolve().parents[5] / "docs/evaluation/answer-quality/answer-quality-v1.json"
GRADER = "vendor/grader"


def _call(*args):
    out = StringIO()
    call_command("eval_answer_quality", "--set", str(SET), *args, stdout=out)
    return out.getvalue()


def test_the_committed_set_has_twelve_families_of_at_least_eight_over_the_proxy_corpus():
    data = json.loads(SET.read_text(encoding="utf-8"))
    assert aq.validate_set(data) == []
    assert len(data["corpus"]["titles"]) == 40
    assert {c["family"] for c in data["cases"]} == set(aq.FAMILIES)
    assert all(c["sources"] for c in data["cases"])
    reused = {s.split(":")[0] for c in data["cases"] for s in c["sources"]}
    assert {"proxy_starter", "conversation_set_v1", "long-context-draft"} <= reused


def test_validate_reports_every_family():
    out = _call("--validate")
    assert "108 questions, valid" in out
    for family in aq.FAMILIES:
        assert family in out


def test_a_lock_is_written_once_and_never_rewritten_with_different_content(tmp_path):
    lock = tmp_path / "lock.json"
    _call("--write-lock", str(lock), "--grader-model", GRADER)
    assert json.loads(lock.read_text())["grader_model"] == GRADER
    _call("--write-lock", str(lock), "--grader-model", GRADER)
    with pytest.raises(CommandError, match="new version"):
        _call("--write-lock", str(lock), "--grader-model", "vendor/another")


def test_scoring_refuses_an_unfrozen_or_differently_graded_set(tmp_path):
    lock = tmp_path / "lock.json"
    _call("--write-lock", str(lock), "--grader-model", GRADER)
    with pytest.raises(CommandError, match="--lock and --grader-model"):
        _call("--run")
    with pytest.raises(CommandError, match="not frozen"):
        _call("--run", "--lock", str(lock), "--grader-model", "vendor/another")


def test_a_paid_run_refuses_before_sending_without_a_runtime_and_enforced_admission(
        tmp_path, settings):
    lock = tmp_path / "lock.json"
    _call("--write-lock", str(lock), "--grader-model", GRADER)
    with pytest.raises(CommandError, match="--runtime-url"):
        _call("--run", "--lock", str(lock), "--grader-model", GRADER)
    settings.AI_DURABLE_ASK = False
    settings.AI_EVIDENCE_DECISION = "off"
    settings.AI_PROVIDER_ADMISSION = "off"
    with pytest.raises(CommandError, match="enforce"):
        _call("--run", "--lock", str(lock), "--grader-model", GRADER,
              "--runtime-url", "http://runtime.invalid", "--runtime-model", "m")


def test_a_lowered_family_minimum_validates_a_draft_but_never_freezes_it(tmp_path):
    data = json.loads(SET.read_text(encoding="utf-8"))
    data["cases"] = [c for c in data["cases"] if c["id"] != "F03-01"]
    short = tmp_path / "short.json"
    short.write_text(json.dumps(data), encoding="utf-8")
    out = StringIO()
    call_command("eval_answer_quality", "--set", str(short), "--validate",
                 "--min-per-family", "7", stdout=out)
    assert "valid" in out.getvalue()
    with pytest.raises(CommandError, match="F03"):
        call_command("eval_answer_quality", "--set", str(short), "--min-per-family", "7",
                     "--write-lock", str(tmp_path / "l.json"), "--grader-model", GRADER)


def test_a_rescore_refuses_unless_admission_enforces(tmp_path, settings):
    lock = tmp_path / "lock.json"
    _call("--write-lock", str(lock), "--grader-model", GRADER)
    settings.AI_PROVIDER_ADMISSION = "off"
    with pytest.raises(CommandError, match="enforce"):
        _call("--rescore", str(tmp_path / "run.json"), "--lock", str(lock),
              "--grader-model", GRADER)


def test_a_runtime_that_charged_nothing_here_or_used_another_model_is_a_condition_problem():
    from apps.ai.management.commands.eval_answer_quality import _served_model_problems

    def rows(*attempts):
        return {"F01-01": {"turns": [{"outcome": "answered",
                                      "physical_attempts": list(attempts)}]}}
    assert "campaign key" in _served_model_problems(rows(), "m")[0]
    assert _served_model_problems(rows({"operation": "llm", "model": "M"}), "m") == []
    assert "other" in _served_model_problems(
        rows({"operation": "llm", "model": "other"}), "m")[0]
