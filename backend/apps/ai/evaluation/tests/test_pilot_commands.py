"""IR-550: the milestone and capacity commands' gates and run files.

No server and no vendor: every outbound HTTP call fails the test, so a paid
burst that is refused is proven to have sent nothing.
"""

import json

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai.admission.tests.support import enforce
from apps.ai.evaluation.campaign import paid_plan

from .test_milestone import BASELINE

ADMISSION_DB = pytest.mark.django_db(transaction=True, databases=["default", "admission"])


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("an IR-550 command reached the network")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("IRIS_EVAL_TOKEN", "test-token")


def _written(directory):
    (path,) = directory.iterdir()
    return json.loads(path.read_text())


@pytest.mark.db_required
@ADMISSION_DB
def test_the_proposed_campaign_cannot_fit_a_hundred_uncached_submissions(settings):
    enforce(settings)
    plan = paid_plan(100)
    assert plan["fits"] is False
    # 100 x 12 attempts > 360 spendable, 100 x US$0.50 > US$11.25, and no
    # per-run active-time cap exists to bound the rest.
    assert {"attempts", "cost_micros", "active_ms"} <= set(plan["blocking"])
    assert plan["claim"] == "unverified"


@pytest.mark.db_required
@ADMISSION_DB
def test_a_paid_burst_that_does_not_fit_sends_nothing_and_stays_unverified(
        settings, tmp_path, token):
    enforce(settings)
    questions = tmp_path / "q.json"
    questions.write_text(json.dumps([f"question {i}" for i in range(100)]))
    out = tmp_path / "runs"
    call_command("eval_pilot_capacity", base_url="http://iris", questions=str(questions),
                 n=100, providers="real", cache="cold", out=str(out))
    run = _written(out)
    assert run["summary"]["claim"] == "unverified"
    assert run["summary"]["submitted"] == 0
    assert "submissions" not in run


def test_a_paid_run_refuses_to_start_without_enforced_admission(settings, tmp_path, token):
    settings.AI_PROVIDER_ADMISSION = "off"
    labels = tmp_path / "set.json"
    labels.write_text(json.dumps(BASELINE))
    with pytest.raises(CommandError, match="AI_PROVIDER_ADMISSION"):
        call_command("eval_pilot_milestone", set=str(labels), tier="synthetic",
                     base_url="http://iris", providers="real", out=str(tmp_path))


def test_a_capacity_burst_needs_enough_distinct_questions(tmp_path, token):
    questions = tmp_path / "q.json"
    questions.write_text(json.dumps(["same"] * 100 + ["other"]))
    with pytest.raises(CommandError, match="2 distinct"):
        call_command("eval_pilot_capacity", base_url="http://iris", questions=str(questions),
                     n=100, providers="fake", cache="cold", out=str(tmp_path))


def test_a_published_run_is_rescored_with_a_reviewers_verdicts(tmp_path):
    labels = tmp_path / "set.json"
    labels.write_text(json.dumps(BASELINE))
    rows = [{"record_key": "flood-gauges", "state": "included"}]
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"providers": "fake", "runs": [
        {"case": "b01", "latency_ms": 10,
         "done": {"mode": "generative", "listing": {"count": {"total": 5}}}},
        {"case": "b02", "latency_ms": 20,
         "done": {"mode": "generative", "listing": {
             "candidates": rows, "topic_count": {"matches": 1}}}},
    ]}))
    reviews = tmp_path / "reviews.json"
    reviews.write_text(json.dumps([{"case": "b02", "reviewer": "Jive Tyler Revalde",
                                    "rubric": "pilot-rubric-v1", "answer_correct": True}]))
    out = tmp_path / "runs"
    call_command("eval_pilot_milestone", set=str(labels), tier="synthetic",
                 from_run=str(run), reviews=str(reviews), out=str(out))
    written = _written(out)
    report = written["report"]
    assert written["rescored_from"] == str(run)
    assert report["metadata_counts"]["exact"] == 1
    assert report["metadata_counts"]["missing"] == []
    assert report["coverage"]["missing"] == ["b03"]
    assert report["answer_quality"]["status"] == "exploratory_single_reviewer"
    assert report["standing"]["evidence"] == "exploratory_inconclusive"
