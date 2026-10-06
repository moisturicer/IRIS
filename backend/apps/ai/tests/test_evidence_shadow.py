"""Reader-invisible shadow decisions on real traffic (IR-466, ADR-035 §4, §10).

Driven through the HTTP boundary for everything a reader could observe, and
through `run_shadow_decision` for the worker's lifecycle. Deterministic fakes
throughout; no vendor, no broker.
"""

import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.ai.composition import CompositionRoot, use_composition_root
from apps.ai.evidence import shadow
from apps.ai.evidence.model_decision import ModelEvidenceDecision
from apps.ai.inference import InferenceTask
from apps.ai.models import (
    Conversation,
    ShadowEvidenceDecision,
    ShadowEvidenceTally,
    Turn,
)
from apps.ai.models.shadow import COMPLETED, FAILED, PENDING, RUNNING, SKIPPED
from apps.ai.providers.fakes import (
    ScriptedLLM,
    ScriptedReranker,
    ScriptedToolCallingLLM,
)
from apps.ai.resilience.llm import breaker_for, reset_llm_breakers
from apps.ai.resilience.rate_limit import Lane, TokenBucket

from ..resilience.tests.test_rate_limit import FakeRedis
from .corpus import (
    FLOOD_QUESTION,
    FLOOD_TEXT,
    ask,
    ask_stream,
    make_record,
    make_user,
)

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

SECRET_ANSWER = "HYPOTHETICAL-DIRECT-ANSWER-TEXT"
SECRET_REASONING = "HIDDEN-REASONING-TEXT"

SHADOW_ON = dict(
    AI_EVIDENCE_DECISION="shadow",
    AI_EVIDENCE_SHADOW_SAMPLE_RATE=1.0,
    AI_QUESTION_RESOLUTION_ENABLED=False,
    AI_CONVERSATION_MEMORY_ENABLED=False,
)


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_llm_breakers()
    yield
    reset_llm_breakers()


@pytest.fixture(autouse=True)
def _apps_logs_reach_caplog():
    """`apps` does not propagate (config/settings/base.py); without this the
    log assertions below would pass on nothing captured."""
    apps_logger = logging.getLogger("apps")
    original = apps_logger.propagate
    apps_logger.propagate = True
    yield
    apps_logger.propagate = original


@pytest.fixture
def shadow_on(settings):
    for key, value in SHADOW_ON.items():
        setattr(settings, key, value)
    return settings


class _CountingEmbedder:
    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if callable(attr):
            def counted(*args, **kwargs):
                self.calls += 1
                return attr(*args, **kwargs)
            return counted
        return attr


class _CountingReranker(ScriptedReranker):
    calls = 0

    def rerank(self, *args, **kwargs):
        type(self).calls += 1
        return super().rerank(*args, **kwargs)


def _root(embedder, *, llm=None, shadow_llm=None, reranker=None):
    return CompositionRoot(
        embedder=embedder,
        reranker=reranker or ScriptedReranker(),
        llm=llm or ScriptedLLM(),
        shadow_llm=shadow_llm,
        permits=lambda record: True,
    )


def _bucket(store=None, budget=1_000_000):
    return TokenBucket(store or FakeRedis(), Lane.SHADOW, budget=budget, window_seconds=60)


def _conversation(user, *, prior=True):
    conversation = Conversation.objects.create(user=user)
    if prior:
        Turn.objects.create(
            conversation=conversation,
            question="what data trained the model?",
            answer="Rainfall gauge data [1].",
            state="generated",
        )
    return conversation


def _ask_once(client, endpoint, conversation, django_capture_on_commit_callbacks, *, execute=False):
    with django_capture_on_commit_callbacks(execute=execute) as callbacks:
        response = endpoint(client, FLOOD_QUESTION, conversation_id=conversation.pk)
        if endpoint is ask_stream:
            body = b"".join(response.streaming_content).decode()
        else:
            body = response.json()
    return response, body, callbacks


def _strip_ids(body):
    if isinstance(body, dict):
        return {k: v for k, v in body.items() if k != "conversation_id"}
    events = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        payload = json.loads(data.removeprefix("data: "))
        events.append((name, _strip_ids(payload)))
    return events


def _pending_row(embedder, space, client_for, captured, **root_kwargs):
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = _conversation(reader)
    with use_composition_root(_root(embedder, **root_kwargs)):
        _ask_once(client_for(reader), ask, conversation, captured)
    return ShadowEvidenceDecision.objects.get()


# -- the flag --------------------------------------------------------------


def test_with_the_flag_off_nothing_is_recorded_or_enqueued(
    settings, embedder, space, client_for, django_capture_on_commit_callbacks
):
    settings.AI_EVIDENCE_DECISION = "off"
    settings.AI_EVIDENCE_SHADOW_SAMPLE_RATE = 1.0
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        _, _, callbacks = _ask_once(
            client_for(reader), ask, _conversation(reader), django_capture_on_commit_callbacks
        )

    assert not ShadowEvidenceDecision.objects.exists()
    assert not any("_enqueue" in repr(cb) for cb in callbacks)


def test_shadow_with_a_zero_sample_rate_records_nothing(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    shadow_on.AI_EVIDENCE_SHADOW_SAMPLE_RATE = 0.0
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        _ask_once(client_for(reader), ask, _conversation(reader), django_capture_on_commit_callbacks)

    assert not ShadowEvidenceDecision.objects.exists()


def test_on_is_rejected_as_an_invalid_flag_value(settings):
    from apps.ai.evidence import evidence_configuration_problems

    settings.AI_EVIDENCE_DECISION = "on"
    (problem,) = evidence_configuration_problems()
    assert "rejected" in problem


def test_the_flag_is_registered_as_a_technique_that_refuses_on():
    from apps.ai.evaluation.techniques import TechniqueError, technique

    flag = technique("evidence_decision")
    assert flag.setting == "AI_EVIDENCE_DECISION"
    assert flag.parse("shadow") == "shadow" and flag.parse("off") == "off"
    with pytest.raises(TechniqueError):
        flag.parse("on")


# -- reader invisibility ---------------------------------------------------


@pytest.mark.parametrize("endpoint", [ask, ask_stream], ids=["ask", "ask_stream"])
def test_shadow_changes_nothing_a_reader_receives(
    settings, endpoint, embedder, space, client_for, django_capture_on_commit_callbacks
):
    for key, value in SHADOW_ON.items():
        setattr(settings, key, value)
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    client = client_for(reader)

    bodies = {}
    for mode in ("off", "shadow"):
        settings.AI_EVIDENCE_DECISION = mode
        with use_composition_root(_root(embedder)):
            response, body, _ = _ask_once(
                client, endpoint, _conversation(reader), django_capture_on_commit_callbacks
            )
        assert response.status_code == 200
        bodies[mode] = _strip_ids(body)

    assert bodies["shadow"] == bodies["off"]
    row = ShadowEvidenceDecision.objects.get()
    assert row.status == PENDING


def test_a_pending_row_carries_the_manifest_and_the_detector_verdict(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)

    prior = Turn.objects.order_by("id").first()
    assert row.manifest["window"] == [
        {"turn_id": prior.pk, "question_chars": len(prior.question), "answer_chars": len(prior.answer)}
    ]
    assert row.manifest["record_scoped"] is False
    assert row.manifest["eligibility_states"] == ["generated"]
    assert len(row.manifest["rule_set_digest"]) == 64
    assert len(row.manifest["prompt_digest"]) == 64
    assert {"temperature", "reasoning_effort", "model"} <= set(row.manifest["generation"])
    assert row.detector["rule_set_digest"] == row.manifest["rule_set_digest"]
    assert "evidence_required" in row.detector
    assert row.decision is None


def test_the_task_is_enqueued_only_after_commit(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        "apps.ai.tasks.decide_evidence_shadow.apply_async",
        lambda args, retry: sent.append((args[0], retry)),
    )
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            ask(client_for(reader), FLOOD_QUESTION, conversation_id=_conversation(reader).pk)
        assert sent == []
        for callback in callbacks:
            callback()

    assert sent == [(ShadowEvidenceDecision.objects.get().pk, False)]


def test_a_failing_enqueue_never_reaches_the_reader(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks, monkeypatch
):
    def broken(*args):
        raise ConnectionError("broker down")

    monkeypatch.setattr("apps.ai.tasks.decide_evidence_shadow.apply_async", broken)
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        response, _, _ = _ask_once(
            client_for(reader), ask, _conversation(reader),
            django_capture_on_commit_callbacks, execute=True,
        )

    assert response.status_code == 200
    assert ShadowEvidenceTally.objects.get(code=shadow.TALLY_ENQUEUE_FAILED).count == 1


def test_a_one_off_question_creates_no_record(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        with django_capture_on_commit_callbacks():
            assert ask(client_for(reader), FLOOD_QUESTION).status_code == 200

    assert not ShadowEvidenceDecision.objects.exists()
    assert not Turn.objects.exists()


def test_the_ai_overview_never_reaches_the_orchestrator(
    shadow_on, embedder, space, client_for, monkeypatch
):
    from django.urls import reverse

    import apps.ai.overview as overview_module
    from apps.ai.orchestrator import ChatOrchestrator

    def refuse(*args, **kwargs):
        raise AssertionError("the AI Overview reached the chat orchestrator")

    monkeypatch.setattr(ChatOrchestrator, "__init__", refuse)
    monkeypatch.setattr("apps.ai.orchestrator.shadow_turn", refuse)
    monkeypatch.setattr("apps.ai.evidence.shadow.shadow_turn", refuse)
    reader = make_user("reader@cit.edu")
    record = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        response = client_for(reader).get(reverse("ai-record-overview", args=[record.pk]))

    assert response.status_code == 200
    assert "orchestrator" not in Path(overview_module.__file__).read_text("utf-8")
    assert not ShadowEvidenceDecision.objects.exists()


# -- the worker ------------------------------------------------------------


def test_a_search_route_executes_no_tool(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    """Only the decision call reaches a vendor: no retrieval, no embedding,
    no rerank, no answer generation."""
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)

    counting = _CountingEmbedder(embedder)
    _CountingReranker.calls = 0
    answer_llm = ScriptedLLM()
    shadow_llm = ScriptedToolCallingLLM(
        [ScriptedToolCallingLLM.calling(arguments='{"query": "flood"}', input_tokens=40, output_tokens=5)]
    )
    root = _root(counting, llm=answer_llm, shadow_llm=shadow_llm, reranker=_CountingReranker())
    with use_composition_root(root):
        outcome = shadow.run_shadow_decision(row.pk, bucket_factory=_bucket)

    assert outcome == shadow.EVENT_DECIDED
    assert counting.calls == 0
    assert _CountingReranker.calls == 0
    assert answer_llm.calls == []
    assert len(shadow_llm.tool_requests) == 1
    row.refresh_from_db()
    assert row.status == COMPLETED
    assert row.decision["reason"] == "search_requested"
    assert row.decision["anomalies"] == ["arguments_supplied"]
    assert row.route == "evidence"
    assert row.parity_matched is True and row.parity_differences == {}


def test_the_decision_call_sees_prior_reader_questions_and_no_answer_text(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    shadow_llm = ScriptedToolCallingLLM([ScriptedToolCallingLLM.calling()])

    shadow.run_shadow_decision(
        row.pk,
        decider_factory=lambda: ModelEvidenceDecision(shadow_llm),
        bucket_factory=_bucket,
    )

    (request,) = shadow_llm.tool_requests
    assert "what data trained the model?" in request.user
    assert FLOOD_QUESTION in request.user
    assert "Rainfall gauge data" not in request.user + request.system
    assert FLOOD_TEXT not in request.user + request.system


def test_the_union_rule_keeps_evidence_when_the_detector_demands_it():
    assert shadow.union_route({"evidence_required": True}, "direct") == "evidence"
    assert shadow.union_route({"evidence_required": False}, "evidence") == "evidence"
    assert shadow.union_route({"evidence_required": False}, "direct") == "direct"
    assert shadow.union_route({}, "direct") == "evidence"


def test_two_workers_racing_one_row_claim_it_once(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)

    first = shadow.claim(row.pk)
    loser_llm = ScriptedToolCallingLLM([])
    outcome = shadow.run_shadow_decision(
        row.pk,
        decider_factory=lambda: ModelEvidenceDecision(loser_llm),
        bucket_factory=_bucket,
    )

    assert first is not None and not first.reclaimed
    assert outcome == shadow.EVENT_NOT_CLAIMED
    assert loser_llm.tool_requests == []
    row.refresh_from_db()
    assert row.status == RUNNING and row.claim_token == first.token and row.claims == 1


def test_a_reclaimed_rows_first_worker_writes_nothing_and_is_counted(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    later = timezone.now() + timedelta(hours=1)
    reclaims = []

    def slow_decision(request):
        # Another worker reclaims the row while this one is still deciding.
        reclaims.append(shadow.claim(row.pk, now=later))
        return ScriptedToolCallingLLM.answering(SECRET_ANSWER)

    llm = ScriptedToolCallingLLM(slow_decision)
    outcome = shadow.run_shadow_decision(
        row.pk, decider_factory=lambda: ModelEvidenceDecision(llm), bucket_factory=_bucket
    )

    assert outcome == shadow.EVENT_FENCED_OUT
    (second,) = reclaims
    assert second is not None and second.reclaimed
    row.refresh_from_db()
    assert row.status == RUNNING and row.claim_token == second.token
    assert row.decision is None and row.route == ""
    assert row.fenced_out_completions == 1
    assert row.reclaims == 1
    assert shadow.coverage()["fenced_out_completions"] == 1


def test_a_stale_running_row_is_reclaimed_once_and_counted(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    start = timezone.now()

    assert shadow.claim(row.pk, now=start) is not None
    assert shadow.claim(row.pk, now=start + timedelta(seconds=10)) is None
    second = shadow.claim(row.pk, now=start + timedelta(hours=1))
    third = shadow.claim(row.pk, now=start + timedelta(hours=3))

    assert second is not None and second.reclaimed
    assert third is None
    row.refresh_from_db()
    assert (row.claims, row.reclaims) == (2, 1)
    assert shadow.coverage()["reclaims"] == 1


def test_a_retry_exhausted_row_lands_failed_and_reports_missing_coverage(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)

    def broken():
        raise TypeError("not a tool-calling provider")

    with pytest.raises(TypeError):
        shadow.run_shadow_decision(row.pk, final_attempt=False, decider_factory=broken)
    row.refresh_from_db()
    assert row.status == PENDING and row.claim_token is None

    outcome = shadow.run_shadow_decision(row.pk, final_attempt=True, decider_factory=broken)

    assert outcome == shadow.FAIL_RETRIES_EXHAUSTED
    row.refresh_from_db()
    assert (row.status, row.outcome) == (FAILED, shadow.FAIL_RETRIES_EXHAUSTED)
    report = shadow.coverage()
    assert report["decided"] == 0 and report["missing"] == 1


def test_the_celery_task_retries_then_fails_the_row(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks, monkeypatch, settings
):
    from apps.ai.tasks import decide_evidence_shadow

    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    monkeypatch.setattr(CompositionRoot, "shadow_decider", lambda self: (_ for _ in ()).throw(TypeError("x")))
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = False

    decide_evidence_shadow.apply(args=[row.pk])

    row.refresh_from_db()
    assert (row.status, row.outcome) == (FAILED, shadow.FAIL_RETRIES_EXHAUSTED)
    assert row.claims == decide_evidence_shadow.max_retries + 1


def test_a_deleted_conversation_cascades_and_its_task_is_a_counted_skip(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)

    Conversation.objects.all().delete()

    assert not ShadowEvidenceDecision.objects.exists()
    assert shadow.run_shadow_decision(row.pk) == shadow.TALLY_TURN_DELETED
    assert ShadowEvidenceTally.objects.get(code=shadow.TALLY_TURN_DELETED).count == 1
    assert shadow.coverage()["missing"] == 1


def test_a_manifest_mismatch_runs_anyway_and_records_what_differed(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    shadow_on.AI_HISTORY_TOKEN_BUDGET = 1
    shadow_on.LLM_TEMPERATURE = 0.7
    llm = ScriptedToolCallingLLM([ScriptedToolCallingLLM.calling()])

    outcome = shadow.run_shadow_decision(
        row.pk, decider_factory=lambda: ModelEvidenceDecision(llm), bucket_factory=_bucket
    )

    assert outcome == shadow.EVENT_DECIDED
    row.refresh_from_db()
    assert row.parity_matched is False
    assert row.parity_differences["history_token_budget"]["task"] == 1
    assert row.parity_differences["generation"]["task"]["temperature"] == 0.7
    assert len(llm.tool_requests) == 1


# -- capacity isolation ----------------------------------------------------


def test_shadow_is_skipped_when_the_answer_breaker_is_open(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    answer = breaker_for(InferenceTask.ANSWER.breaker_key)
    for _ in range(5):
        with pytest.raises(ValueError):
            answer.call(lambda: (_ for _ in ()).throw(ValueError("down")))
    llm = ScriptedToolCallingLLM([])

    outcome = shadow.run_shadow_decision(
        row.pk, decider_factory=lambda: ModelEvidenceDecision(llm), bucket_factory=_bucket
    )

    assert outcome == shadow.SKIP_ANSWER_BREAKER_OPEN
    assert llm.tool_requests == []
    row.refresh_from_db()
    assert (row.status, row.outcome) == (SKIPPED, shadow.SKIP_ANSWER_BREAKER_OPEN)
    assert shadow.coverage()["missing"] == 1


def test_a_question_asked_while_the_answer_breaker_is_open_is_skipped_in_request(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    """Breakers are per process, so the reader's breaker is read where reader
    calls trip it -- in the web request -- and nothing is enqueued."""
    answer = breaker_for(InferenceTask.ANSWER.breaker_key)
    for _ in range(5):
        with pytest.raises(ValueError):
            answer.call(lambda: (_ for _ in ()).throw(ValueError("down")))
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        response, _, callbacks = _ask_once(
            client_for(reader), ask, _conversation(reader), django_capture_on_commit_callbacks
        )

    assert response.status_code == 200
    row = ShadowEvidenceDecision.objects.get()
    assert (row.status, row.outcome) == (SKIPPED, shadow.SKIP_ANSWER_BREAKER_OPEN)
    assert row.finished_at is not None
    assert not any("_enqueue" in repr(cb) for cb in callbacks)
    assert shadow.coverage()["missing"] == 1


def test_shadow_is_skipped_when_the_answer_breaker_has_recent_failures(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    with pytest.raises(ValueError):
        breaker_for(InferenceTask.ANSWER.breaker_key).call(
            lambda: (_ for _ in ()).throw(ValueError("down"))
        )

    outcome = shadow.run_shadow_decision(
        row.pk,
        decider_factory=lambda: ModelEvidenceDecision(ScriptedToolCallingLLM([])),
        bucket_factory=_bucket,
    )

    assert outcome == shadow.SKIP_ANSWER_BREAKER_FAILURES


def test_shadow_is_skipped_when_its_budget_is_spent(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    llm = ScriptedToolCallingLLM([])

    outcome = shadow.run_shadow_decision(
        row.pk,
        decider_factory=lambda: ModelEvidenceDecision(llm),
        bucket_factory=lambda: _bucket(budget=10),
    )

    assert outcome == shadow.SKIP_BUDGET_SPENT
    assert llm.tool_requests == []


def test_shadow_spend_is_reconciled_to_what_the_call_used(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    store = FakeRedis()
    llm = ScriptedToolCallingLLM(
        [ScriptedToolCallingLLM.calling(input_tokens=300, output_tokens=20)]
    )

    shadow.run_shadow_decision(
        row.pk, decider_factory=lambda: ModelEvidenceDecision(llm),
        bucket_factory=lambda: _bucket(store),
    )

    assert list(store.store.values()) == [320]
    assert all(":shadow:" in key for key in store.store)


def test_the_reader_path_spends_against_no_bucket(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks, monkeypatch
):
    def refuse(*args, **kwargs):
        raise AssertionError("the reader path reached a rate-limit bucket")

    monkeypatch.setattr("apps.ai.resilience.rate_limit.bucket_for", refuse)
    monkeypatch.setattr("apps.ai.resilience.rate_limit.TokenBucket.spend", refuse)
    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)

    with use_composition_root(_root(embedder)):
        for endpoint in (ask, ask_stream):
            response, _, _ = _ask_once(
                client_for(reader), endpoint, _conversation(reader),
                django_capture_on_commit_callbacks,
            )
            assert response.status_code == 200


# -- what is never kept ----------------------------------------------------


def test_no_hypothetical_answer_or_reasoning_is_kept_or_logged(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks, caplog
):
    caplog.set_level(logging.DEBUG)
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    turn_before = Turn.objects.filter(pk=row.turn_id).values().get()
    llm = ScriptedToolCallingLLM(
        [ScriptedToolCallingLLM.answering(SECRET_ANSWER, reasoning=SECRET_REASONING)]
    )

    shadow.run_shadow_decision(
        row.pk, decider_factory=lambda: ModelEvidenceDecision(llm), bucket_factory=_bucket
    )

    row.refresh_from_db()
    stored = json.dumps(
        [row.manifest, row.detector, row.decision, row.parity_differences]
    )
    assert SECRET_ANSWER not in stored and SECRET_REASONING not in stored
    assert row.decision["answer_present"] is True
    assert row.decision["answer_chars"] == len(SECRET_ANSWER)
    assert Turn.objects.filter(pk=row.turn_id).values().get() == turn_before
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert SECRET_ANSWER not in logged and SECRET_REASONING not in logged


def test_shadow_logs_carry_turn_ids_and_codes_only(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks, caplog
):
    caplog.set_level(logging.DEBUG, logger="apps.ai.evidence.shadow")
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    llm = ScriptedToolCallingLLM([ScriptedToolCallingLLM.calling()])

    shadow.run_shadow_decision(
        row.pk, decider_factory=lambda: ModelEvidenceDecision(llm), bucket_factory=_bucket
    )

    records = [r for r in caplog.records if r.name == "apps.ai.evidence.shadow"]
    assert records
    for record in records:
        message = record.getMessage()
        assert message.startswith("evidence shadow ")
        for text in (FLOOD_QUESTION, FLOOD_TEXT, "what data trained the model?", "Rainfall"):
            assert text not in message
        # Ids and codes only: every argument is a code string or a Turn id.
        assert all(isinstance(arg, (str, int, bool, type(None))) for arg in record.args)


def test_a_decision_that_raises_hands_its_reservation_back(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)
    store = FakeRedis()
    llm = ScriptedToolCallingLLM([TypeError("unexpected")])

    with pytest.raises(TypeError):
        shadow.run_shadow_decision(
            row.pk,
            final_attempt=False,
            decider_factory=lambda: ModelEvidenceDecision(llm),
            bucket_factory=lambda: _bucket(store),
        )

    assert list(store.store.values()) == [0]


def test_a_fenced_final_attempt_reports_fenced_not_failed(
    shadow_on, embedder, space, client_for, django_capture_on_commit_callbacks
):
    row = _pending_row(embedder, space, client_for, django_capture_on_commit_callbacks)

    def reclaimed_then_broken():
        shadow.claim(row.pk, now=timezone.now() + timedelta(hours=1))
        raise TypeError("x")

    outcome = shadow.run_shadow_decision(
        row.pk, final_attempt=True, decider_factory=reclaimed_then_broken
    )

    assert outcome == shadow.EVENT_FENCED_OUT
    row.refresh_from_db()
    assert row.status == RUNNING and row.outcome == ""
