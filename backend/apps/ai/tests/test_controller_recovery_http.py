"""Durable recovery fences at HTTP submission and real admission boundaries."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ai import durable
from apps.ai.admission import errors, scope
from apps.ai.admission.ledger import Request, admit
from apps.ai.composition import use_composition_root
from apps.ai.controller.versions import CONTROLLER_ENGINE, pin
from apps.ai.models import AskRun, ProviderReservation, Turn
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import StreamDelta
from apps.ai.tasks import answer_queued_question

from . import test_durable_ask_http as http
from .corpus import root_with
from . import test_admission_http as admitted

scene = admitted.scene
dispatched = admitted.dispatched
queued = admitted.queued

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]


def _submit(scene, dispatched, capture):
    return http._submit(scene["client"], scene["conversation"], dispatched, capture)[0]


def _deny_new_call(run, attempt=None):
    request = Request(
        operation="llm", default_lane="chat", account="acct-a", models=("cheap",),
        input_tokens=1, output_tokens=1, timeout_seconds=1,
    )
    with scope.run(durable.run_scope(run, attempt)):
        with pytest.raises(errors.AdmissionDenied) as denied:
            admit(request)
    assert denied.value.reason == errors.RUN_CANCELLED
    assert not ProviderReservation.objects.using("admission").exists()


def test_superseded_delivery_cannot_admit_a_new_paid_attempt(
    scene, dispatched, django_capture_on_commit_callbacks,
):
    run_id = _submit(scene, dispatched, django_capture_on_commit_callbacks)
    old = durable.claim(run_id)
    current = durable.claim(run_id)
    _deny_new_call(AskRun.objects.get(pk=run_id), old)
    assert not durable.run_scope(AskRun.objects.get(pk=run_id), current).halted()
    with pytest.raises(durable.StaleAttempt):
        durable.append(old, "activity", {"state": "thinking"})


@pytest.mark.parametrize("state", ["cancelled", "failed", "expired", "succeeded", "partial", "deleted", "deadline"])
def test_stopped_work_cannot_admit_a_new_paid_attempt(
    state, scene, dispatched, django_capture_on_commit_callbacks,
):
    run_id = _submit(scene, dispatched, django_capture_on_commit_callbacks)
    run = AskRun.objects.get(pk=run_id)
    if state == "deleted":
        run.delete()
    elif state == "deadline":
        AskRun.objects.filter(pk=run_id).update(deadline_at=timezone.now() - timedelta(seconds=1))
    else:
        AskRun.objects.filter(pk=run_id).update(state=state)
    _deny_new_call(run)


@pytest.mark.parametrize("field", ["engine", "protocol", "prompt", "answer_prompt"])
def test_unsupported_pin_fails_before_preparation_or_resolver(
    field, scene, dispatched, monkeypatch, django_capture_on_commit_callbacks,
):
    run_id = _submit(scene, dispatched, django_capture_on_commit_callbacks)
    run = AskRun.objects.get(pk=run_id)
    versions = pin(CONTROLLER_ENGINE)
    versions[field] = "unavailable-version"
    run.request["pin"] = versions
    run.save(update_fields=["request"])

    def unexpected_preparation(*args, **kwargs):
        pytest.fail("unsupported pins must not reach preparation or its paid resolver")

    monkeypatch.setattr("apps.ai.views.chatbot.prepare_ask", unexpected_preparation)
    with use_composition_root(scene["root"]):
        answer_queued_question(run_id)
    _, frames = http._follow(scene["client"], run_id)
    assert frames[-1][1:] == ("run_failed", {
        "run_id": run_id, "state": "failed", "reason": "engine_unavailable",
    })
    assert not Turn.objects.exists()
    assert scene["adapter"].sent == 0
    assert not ProviderReservation.objects.using("admission").exists()


def test_unpinned_pre_controller_run_still_finishes_under_legacy_engine(
    scene, dispatched, django_capture_on_commit_callbacks,
):
    run_id = _submit(scene, dispatched, django_capture_on_commit_callbacks)
    run = AskRun.objects.get(pk=run_id)
    run.request.pop("pin")
    run.save(update_fields=["request"])
    with use_composition_root(scene["root"]):
        answer_queued_question(run_id)
    _, frames = http._follow(scene["client"], run_id)
    assert frames[-1][1] == "done"
    assert Turn.objects.count() == 1


def test_provider_finishing_after_deadline_cannot_commit_a_late_turn(
    scene, embedder, dispatched, django_capture_on_commit_callbacks,
):
    run_id = _submit(scene, dispatched, django_capture_on_commit_callbacks)

    class LateAnswer(ScriptedLLM):
        def stream(self, system, user):
            yield StreamDelta(text="Rainfall gauges ")
            AskRun.objects.filter(pk=run_id).update(
                deadline_at=timezone.now() - timedelta(seconds=1),
            )
            yield StreamDelta(text="feed the model [1].")

    with use_composition_root(root_with(embedder=embedder, llm=LateAnswer())):
        answer_queued_question(run_id)
    assert not Turn.objects.exists()
    _, frames = http._follow(scene["client"], run_id)
    assert frames[-1][1:] == ("run_failed", {
        "run_id": run_id, "state": "expired", "reason": "deadline_exceeded",
    })
    assert sum(name in ("done", "run_failed", "run_cancelled") for _, name, _ in frames) == 1
