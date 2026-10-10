"""The experiment's controls, failures and denominators without vendor calls."""

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from django.core.management import call_command

from apps.ai.evaluation.answer_models import (
    ModelSpec, diagnostics, experiment, padded_prompt, read_judgement,
)
from apps.ai.providers.measured import MeasuredCompletion
from apps.ai.providers.openai_compatible import OpenAICompatibleAdapter, LLMUnavailable
from apps.ai.providers.dialects import OpenRouterDialect


def spec(maker="openai"):
    return ModelSpec(maker + "/model", maker, "pinned-build", ("us-host",),
                     200000, 0.1, 0.5, "catalogue", "2026-10-10", max_tokens=100)


def snapshot():
    return {"version": 1, "tier": "proxy", "cases": [
        {"id": "q1", "question": "What is supported?", "reference": "Fact.",
         "prompt": "Question: What is supported?\nSources:\n[1] Fact.", "source_count": 1}]}


SCORES = json.dumps({"correctness": 1, "claim_support": 1, "citation_support": 1,
                     "reasoning_leakage": False, "rationale": "Supported."})


def test_frozen_prompt_reused_across_models_and_repeats():
    calls = []

    def complete(model, system, user):
        calls.append((model.maker, user))
        return MeasuredCompletion(SCORES if model.maker == "anthropic" else "Fact. [1]",
                                  cost=0.01, finish_reason="stop")

    result = experiment(snapshot(), [spec(), replace(spec(), model="openai/other")],
                        [spec("anthropic")], complete, arms=[0], counter=len)
    assert len(result["rows"]) == 4
    assert len({prompt for maker, prompt in calls if maker == "openai"}) == 1
    assert result["complete"] is True
    assert result["summary"][0]["correctness"] == 1


def test_self_judging_refused_even_with_same_vendor_transport():
    with pytest.raises(ValueError, match="independent"):
        experiment(snapshot(), [spec()], [spec()], None)


def test_one_repeat_refused():
    with pytest.raises(ValueError, match="two repeats"):
        experiment(snapshot(), [spec()], [spec("anthropic")], None, repeats=1)


def test_empty_length_and_malformed_judge_are_observable():
    def complete(model, system, user):
        return MeasuredCompletion("" if model.maker == "openai" else "not JSON",
                                  finish_reason="length", output_tokens=100, reasoning_tokens=100)

    result = experiment(snapshot(), [spec()], [spec("anthropic")], complete,
                        arms=[0], counter=len)
    summary = result["summary"][0]
    assert summary["empty_content_rate"] == summary["length_finish_rate"] == 1
    assert summary["judged"] == 0
    assert summary["correctness"] is None
    assert all("judge_error" in r for r in result["rows"])


def test_failures_are_counted_and_checkpointed():
    saved = []

    def unavailable(*args):
        raise LLMUnavailable("offline")

    result = experiment(snapshot(), [spec()], [spec("anthropic")], unavailable,
                        arms=[0], counter=len, checkpoint=lambda r: saved.append(len(r["rows"])))
    assert saved == [1, 2]
    assert result["summary"][0]["errors"] == 2


def test_context_arm_skipped_before_any_call():
    result = experiment(snapshot(), [replace(spec(), context_tokens=1000)],
                        [spec("anthropic")], None, arms=[150000], counter=len)
    assert all(r["skip"] == "context_limit" for r in result["rows"])


def test_history_padding_size_and_current_question():
    prompt, count = padded_prompt(snapshot()["cases"][0], 25000, len)
    assert 25000 <= count < 25100
    assert prompt.endswith(snapshot()["cases"][0]["prompt"])


@pytest.mark.parametrize("value", [True, -1, 2, float("nan")])
def test_invalid_judge_scores_refused(value):
    scores = json.loads(SCORES)
    scores["correctness"] = value
    with pytest.raises(ValueError):
        read_judgement(json.dumps(scores))


def test_citation_drift_invalid_marker_and_think_leak():
    result = diagnostics("<think>reason</think> Fact 【1†L1】 [99]", 1)
    assert result["citation_format_drift"] and result["think_tag_leak"]
    assert result["invalid_citations"] == [99]
    assert diagnostics("[99, 100] 【98】", 1)["invalid_citations"] == [98, 99, 100]


def test_failed_answers_reduce_correctness_bounds():
    calls = 0

    def complete(model, system, user):
        nonlocal calls
        if model.maker == "openai":
            calls += 1
            if calls == 2:
                raise LLMUnavailable("offline")
        return MeasuredCompletion(SCORES if model.maker == "anthropic" else "Fact [1]")

    report = experiment(snapshot(), [spec()], [spec("anthropic")], complete,
                        arms=[0], counter=len)
    assert report["summary"][0]["correctness"] == 1
    assert report["summary"][0]["correctness_lower_bound"] == 0.5
    assert report["summary"][0]["correctness_upper_bound"] == 0.5


def test_run_cap_stops_before_call():
    report = experiment(snapshot(), [spec()], [spec("anthropic")],
                        lambda *_: pytest.fail("must not call"), arms=[0], counter=len,
                        max_run_cost_usd=0.000001)
    assert all(r["skip"] == "run_budget" for r in report["rows"])


def test_capture_validation_is_offline(tmp_path, monkeypatch):
    from apps.ai.management.commands import capture_answer_snapshot
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"tier": "proxy", "questions": [
        {"id": "a", "question": "a", "reference": "a"}]}))
    monkeypatch.setattr(capture_answer_snapshot, "composition_root", lambda: pytest.fail("retrieval"))
    call_command("capture_answer_snapshot", questions=str(labels), user="fake@example.test",
                 out=str(tmp_path / "snapshot.json"))
    assert not (tmp_path / "snapshot.json").exists()


def test_measured_response_and_luna_request_shape():
    calls = []
    response = SimpleNamespace(model="actual-build", provider="us-host", id="id",
        choices=[SimpleNamespace(message=SimpleNamespace(content="", reasoning="Thinking"), finish_reason="length")],
        usage=SimpleNamespace(prompt_tokens=40, completion_tokens=100, cost=0.02,
                              completion_tokens_details=SimpleNamespace(reasoning_tokens=100)))

    def create(**kwargs):
        calls.append(kwargs)
        return response

    adapter = OpenAICompatibleAdapter(model="openai/gpt-6-luna", max_tokens=100,
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        dialect=OpenRouterDialect(provider_only=("us-host",)))
    answer = adapter.complete_measured("system", "question")
    assert answer.text == "" and answer.reasoning_tokens == 100
    assert answer.model == "actual-build" and answer.cost == 0.02
    assert calls[0]["max_completion_tokens"] == 100 and "max_tokens" not in calls[0]
    assert calls[0]["extra_body"]["provider"] == {"only": ["us-host"], "data_collection": "deny"}
    with pytest.raises(LLMUnavailable, match="empty"):
        adapter.generate("system", "question")


def test_command_dry_run_never_constructs_client(tmp_path, monkeypatch):
    from dataclasses import asdict
    a = tmp_path / "snapshot.json"
    b = tmp_path / "manifest.json"
    a.write_text(json.dumps(snapshot()))
    b.write_text(json.dumps({"candidates": [asdict(spec())], "judges": [asdict(spec("anthropic"))], "arms": [0]}))
    monkeypatch.setattr(OpenAICompatibleAdapter, "_build_client", lambda *_: pytest.fail("network call"))
    call_command("eval_answers", snapshot=str(a), manifest=str(b), out=str(tmp_path / "run.json"))
    assert not (tmp_path / "run.json").exists()
