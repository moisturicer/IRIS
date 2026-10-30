"""IR-609: eval_campaign and the held-out gate end to end. No database, no vendor."""

import json

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.evaluation.campaign_report import CampaignRefused, require_frozen_for_held_out
from apps.ai.evaluation.conversation_scoring import TARGETS

from .test_campaign_report import (APPROVED, LOCK, PASSED, SET, campaign_reviews, conv, make_set,
                                   reps, smoke_run)
from apps.ai.evaluation.conversations import lock_record


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("eval_campaign reached the network")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


def _write(path, value):
    path.write_text(json.dumps(value))
    return str(path)


def _report_inputs(tmp_path, reviews=None):
    runs = [f"controller={_write(tmp_path / f'r{i}.json', r)}"
            for i, r in enumerate(reps("controller"))]
    return dict(set=_write(tmp_path / "set.json", SET), lock=_write(tmp_path / "lock.json", LOCK),
                runs=runs, reviews=_write(tmp_path / "reviews.json",
                                          campaign_reviews() if reviews is None else reviews),
                approvals=_write(tmp_path / "approvals.json", APPROVED),
                scenarios=_write(tmp_path / "scenarios.json", {"scenarios": PASSED}),
                out=str(tmp_path / "out"))


def test_report_writes_json_and_markdown(tmp_path):
    call_command("eval_campaign", report=True, min_examples=4, **_report_inputs(tmp_path))
    (written,) = (tmp_path / "out").glob("*.json")
    report = json.loads(written.read_text())
    assert report["arms"]["controller"]["status"] == "measured"
    assert report["arms"]["current"]["status"] == "not_measured"
    assert report["enablement_blocked"] is False
    markdown = written.with_suffix(".md").read_text(encoding="utf-8")
    assert "7/8" in markdown and "not_measured" in markdown


def test_report_refuses_unequal_arms(tmp_path):
    inputs = _report_inputs(tmp_path)
    inputs["runs"] += [f"current={_write(tmp_path / f'c{i}.json', r)}"
                       for i, r in enumerate(reps("current", data_policy="retains"))]
    with pytest.raises(CommandError, match="data_policy"):
        call_command("eval_campaign", report=True, min_examples=4, **inputs)


def test_counted_report_refuses_a_lowered_family_minimum(tmp_path):
    with pytest.raises(CommandError, match="minimum"):
        call_command("eval_campaign", report=True, counted=True, min_examples=4,
                     **_report_inputs(tmp_path))


def test_excluded_runs_are_listed_with_their_reason(tmp_path):
    inputs = _report_inputs(tmp_path)
    call_command("eval_campaign", report=True, min_examples=4,
                 exclude_run=["stale-1=collected before the lock"], **inputs)
    (written,) = (tmp_path / "out").glob("*.json")
    assert json.loads(written.read_text())["excluded_runs"] == [
        {"run_id": "stale-1", "reason": "collected before the lock"}]


def test_smoke_reports_spend_and_readiness(tmp_path):
    path = _write(tmp_path / "smoke.json", smoke_run())
    call_command("eval_campaign", smoke=path, case_cost_usd=0.1, campaign_cost_usd=2.0,
                 planned_cases=20, out=str(tmp_path / "out"))
    (written,) = (tmp_path / "out").glob("*.json")
    summary = json.loads(written.read_text())
    assert summary["max_conversation_cost_usd"] == pytest.approx(0.07)
    assert summary["ready"] is False


# --- held-out freeze -------------------------------------------------------


def test_held_out_opens_only_after_lock_rubric_and_thresholds_froze():
    with pytest.raises(CampaignRefused, match="locked_at"):
        require_frozen_for_held_out(SET, {**LOCK, "locked_at": None})
    unpinned = {k: v for k, v in LOCK.items() if k != "thresholds"}
    with pytest.raises(CampaignRefused, match="thresholds"):
        require_frozen_for_held_out(SET, unpinned)
    frozen = {**unpinned, "thresholds": dict(TARGETS)}
    require_frozen_for_held_out(SET, frozen)
    with pytest.raises(CampaignRefused, match="thresholds"):
        require_frozen_for_held_out(SET, {**frozen, "thresholds": {"task_completion": 0.5}})


def test_a_new_lock_records_the_thresholds_it_froze():
    assert lock_record(SET)["thresholds"] == TARGETS


def _held_out_inputs(tmp_path, lock):
    data = make_set([conv("h1", split="held_out")], label_status="human_reviewed",
                    labelled_by=["Ana Reyes"])
    return (_write(tmp_path / "set.json", data),
            _write(tmp_path / "lock.json", {**lock_record(data), **lock}))


def test_replay_refuses_held_out_before_the_freeze(tmp_path):
    set_path, lock_path = _held_out_inputs(tmp_path, {"thresholds": None})
    with pytest.raises(CommandError, match="locked_at"):
        call_command("eval_replay_conversations", set=set_path, lock=lock_path, case=["h1"],
                     held_out=True)


def test_replay_refuses_paid_held_out_without_approvals(tmp_path):
    set_path, lock_path = _held_out_inputs(tmp_path, {"locked_at": "2026-10-01T00:00:00+00:00"})
    with pytest.raises(CommandError, match="approvals"):
        call_command("eval_replay_conversations", set=set_path, lock=lock_path, case=["h1"],
                     held_out=True, providers="real",
                     approvals=_write(tmp_path / "a.json", {"funding": APPROVED["funding"]}))


def test_replay_held_out_flag_takes_held_out_cases_only(tmp_path):
    data = make_set([conv("d1")])
    set_path = _write(tmp_path / "set.json", data)
    lock_path = _write(tmp_path / "lock.json",
                       {**lock_record(data), "locked_at": "2026-10-01T00:00:00+00:00"})
    with pytest.raises(CommandError, match="held-out case"):
        call_command("eval_replay_conversations", set=set_path, lock=lock_path, case=["d1"],
                     held_out=True)
