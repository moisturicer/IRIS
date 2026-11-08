"""IR-956: the committed set and the command's free steps. No database, no vendor."""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from apps.ai.evaluation import answer_quality as aq

SET = Path(__file__).resolve().parents[5] / "docs/evaluation/answer-quality/answer-quality-v2.json"
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


def test_the_committed_lock_freezes_the_committed_set_with_its_pinned_grader():
    lock = json.loads(SET.with_name("answer-quality-v2.lock.json").read_text(encoding="utf-8"))
    data = json.loads(SET.read_text(encoding="utf-8"))
    assert lock["grader_model"] == "anthropic/claude-haiku-5.5"
    assert aq.check_lock(data, lock, grader_model=lock["grader_model"]) == []


def test_every_request_carries_a_fresh_token_from_a_tracked_session():
    from types import SimpleNamespace

    from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

    from apps.ai.management.commands.eval_answer_quality import _bearer

    started, now = [], [0.0]

    def start(user):
        refresh = RefreshToken()
        refresh["user_id"] = user.id
        refresh["sid"] = f"s{len(started)}"
        started.append(refresh)
        return refresh

    headers = _bearer(SimpleNamespace(id=7, pk=7), start=start, clock=lambda: now[0],
                      idle_seconds=60)
    first, second = headers()["Authorization"], headers()["Authorization"]
    assert first.startswith("Bearer ") and first != second and len(started) == 1
    token = AccessToken(second.removeprefix("Bearer "))
    assert str(token["user_id"]) == "7" and token["sid"] == "s0"
    now[0] = 61.0
    assert AccessToken(headers()["Authorization"].removeprefix("Bearer "))["sid"] == "s1"


def test_a_campaign_attempt_no_case_accounts_for_is_a_condition_problem():
    from apps.ai.management.commands.eval_answer_quality import _stray_attempts

    rows = {"django": {"F01-01": {"turns": [{"physical_attempts": [{"id": 11}]}]}},
            "agent": {"F01-01": {"turns": [{"physical_attempts": [{"id": 12}]}]}}}
    assert _stray_attempts([{"id": 11}, {"id": 12}], rows) == []
    assert "13" in _stray_attempts([{"id": 11}, {"id": 13}], rows)[0]


def test_gateway_requests_carry_what_the_edge_would_and_no_reader_token():
    from apps.ai.management.commands.eval_answer_quality import _edge_headers

    asked = []

    def fetch(record_id):
        asked.append(record_id)
        return f"grant-{len(asked)}"

    headers = _edge_headers(fetch, secret="s3cret", record_id=71)
    first, second = headers(), headers()
    assert first == {"X-IRIS-Reader-Grant": "grant-1", "X-IRIS-Protocol": "runs-reader-1",
                     "X-IRIS-Service-Secret": "s3cret", "X-IRIS-Record": "71"}
    assert second["X-IRIS-Reader-Grant"] == "grant-2" and asked == [71, 71]
    assert "X-IRIS-Record" not in _edge_headers(fetch, secret="s", record_id=None)()


def test_a_refused_edge_grant_stops_the_request():
    from apps.ai.management.commands.eval_answer_quality import _edge_headers

    with pytest.raises(CommandError, match="grant"):
        _edge_headers(lambda record_id: None, secret="s", record_id=None)()


def test_in_process_requests_use_a_host_django_allows(settings):
    from types import SimpleNamespace

    from apps.ai.management.commands.eval_answer_quality import _Reader

    settings.ALLOWED_HOSTS = ["iris.example", "*.example"]
    reader = _Reader(SimpleNamespace(id=7, pk=7))
    assert reader.client.defaults["HTTP_HOST"] == "iris.example"


def test_a_paper_the_disclosure_gate_withholds_is_a_condition_problem():
    from types import SimpleNamespace

    from apps.ai.management.commands.eval_answer_quality import _withheld_problems

    papers = [SimpleNamespace(pk=20, title="Open"), SimpleNamespace(pk=21, title="Held")]
    explain = {20: None, 21: "the author has not consented to this disclosure"}
    assert _withheld_problems(papers[:1], explain.get) == []
    problems = _withheld_problems(papers, explain.get)
    assert len(problems) == 1 and "1 of 2" in problems[0] and "consented" in problems[0]


def test_preflight_prices_every_model_django_may_call_including_the_router(settings):
    from apps.ai.management.commands.eval_answer_quality import _django_models
    from apps.ai.providers.openrouter_decisions import PINNED_MODEL

    settings.LLM_ROUTE_MODEL = "vendor/router-backup"
    settings.AI_JEV_ROUTING_ENABLED = True
    assert {PINNED_MODEL, "vendor/router-backup"} <= _django_models()
    settings.AI_JEV_ROUTING_ENABLED = False
    assert PINNED_MODEL not in _django_models()


def test_a_throttled_edge_grant_is_not_mistaken_for_a_refusal():
    from types import SimpleNamespace

    from apps.ai.management.commands.eval_answer_quality import _grant_fetcher

    reader = SimpleNamespace(_fresh=lambda: SimpleNamespace(
        get=lambda *a, **k: SimpleNamespace(status_code=429, headers={})))
    with pytest.raises(CommandError, match="HTTP 429"):
        _grant_fetcher(reader)(None)


def test_preflight_refuses_rate_limits_the_run_would_hit(settings):
    from apps.ai.management.commands.eval_answer_quality import _throttle_problems

    rates = dict(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                 ai_query="60/hour", user="1000/day")
    settings.REST_FRAMEWORK = dict(settings.REST_FRAMEWORK, DEFAULT_THROTTLE_RATES=rates)
    problems = _throttle_problems(turns=120)
    assert any("ai_query" in p for p in problems)
    rates.update(ai_query="100000/hour", user="100000/hour")
    assert _throttle_problems(turns=120) == []


def test_a_token_minted_late_in_a_session_is_not_already_expired():
    from datetime import timedelta
    from types import SimpleNamespace

    from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
    from rest_framework_simplejwt.utils import aware_utcnow, datetime_to_epoch

    from apps.ai.management.commands.eval_answer_quality import _bearer

    def start(user):
        refresh = RefreshToken()
        refresh["user_id"], refresh["sid"] = user.id, "s0"
        refresh.current_time = aware_utcnow() - timedelta(minutes=40)
        return refresh

    headers = _bearer(SimpleNamespace(id=7, pk=7), start=start)
    token = AccessToken(headers()["Authorization"].removeprefix("Bearer "))
    assert token["exp"] > datetime_to_epoch(aware_utcnow())
