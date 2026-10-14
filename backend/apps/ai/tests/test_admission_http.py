"""Queued questions under shared provider admission, over HTTP (IR-545).

The chat model is a metered fake behind the real admission decorator, so
reservations are made and settled in the real database while no vendor is
reached and nothing is billed. Everything else comes from the same fakes as
`test_durable_ask_http.py`, which incur no charge at all.
"""

import pytest
from django.urls import reverse

from apps.ai.admission.llm import AdmittedLLMProvider
from apps.ai.admission.tests.support import MeteredAdapter, enforce
from apps.ai.composition import use_composition_root
from apps.ai.models import AskRun, Conversation, ProviderReservation
from apps.ai.models.admission import SETTLED
from apps.ai.tasks import answer_queued_question

from . import test_durable_ask_http as durable_http
from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask_stream, make_record, make_user, root_with

pytestmark = [
    pytest.mark.db_required,
    pytest.mark.django_db(transaction=True, databases=["default", "admission"]),
]


@pytest.fixture(autouse=True)
def queued(settings):
    settings.AI_DURABLE_ASK = True
    settings.AI_DURABLE_ASK_POLL_SECONDS = 0
    settings.AI_RESEARCH_LANE = "off"
    settings.AI_JEV_ROUTING_ENABLED = False
    enforce(settings)
    return settings


@pytest.fixture
def dispatched(monkeypatch):
    sent = []
    monkeypatch.setattr(
        answer_queued_question, "apply_async", lambda args, **limits: sent.append(args[0]),
    )
    return sent


@pytest.fixture
def scene(embedder, space, client_for):
    reader = make_user("reader@cit.edu")
    flood = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    adapter = MeteredAdapter(stream_usage=(150, 12))
    return {
        "reader": reader, "client": client_for(reader), "flood": flood, "adapter": adapter,
        "conversation": Conversation.objects.create(user=reader),
        "root": root_with(embedder=embedder, llm=AdmittedLLMProvider(adapter)),
    }


def _reservations():
    return ProviderReservation.objects.using("admission")


def _answer(scene, dispatched, capture):
    run_id, _ = durable_http._submit(scene["client"], scene["conversation"], dispatched, capture)
    with use_composition_root(scene["root"]):
        answer_queued_question(run_id)
    _, frames = durable_http._follow(scene["client"], run_id)
    return run_id, frames


def test_a_queued_answer_is_admitted_to_its_own_run(scene, dispatched, django_capture_on_commit_callbacks):
    run_id, frames = _answer(scene, dispatched, django_capture_on_commit_callbacks)

    assert frames[-1][1] == "done"
    assert frames[-1][2]["answer"] == "Rainfall gauges feed the model [1]."
    assert "capacity_limited" not in [frame[1] for frame in frames]
    (row,) = _reservations()
    assert (row.run_key, row.lane, row.state) == (f"ask:{run_id}", "chat", SETTLED)
    assert (row.charge_input_tokens, row.charge_output_tokens) == (150, 12)


def test_every_vendor_call_is_bounded_by_the_original_deadline(
    scene, dispatched, django_capture_on_commit_callbacks
):
    scene["adapter"]._timeout = 120.0
    _answer(scene, dispatched, django_capture_on_commit_callbacks)
    (timeout,) = scene["adapter"].timeouts
    assert timeout <= 30, "the run's 30 s from submission, not the call's own 120 s"


def test_an_exhausted_campaign_says_busy_and_keeps_the_sources(
    scene, dispatched, settings, django_capture_on_commit_callbacks
):
    enforce(settings, AI_ADMISSION_CAMPAIGN_MAX_COST_USD="0.000001")
    run_id, frames = _answer(scene, dispatched, django_capture_on_commit_callbacks)

    names = [frame[1] for frame in frames]
    assert names[-2:] == ["capacity_limited", "done"]
    assert frames[-2][2] == {"status": "busy", "reasons": ["campaign_exhausted"]}
    done = frames[-1][2]
    assert done["mode"] == "unavailable", "explicitly unavailable, not an invented answer"
    assert [source["id"] for source in done["sources"]] == [scene["flood"].pk]
    assert scene["adapter"].sent == 0 and not _reservations().exists()
    assert AskRun.objects.get(pk=run_id).state == "succeeded"


def test_the_queue_is_bounded_and_fair_between_askers(
    scene, dispatched, settings, client_for, django_capture_on_commit_callbacks
):
    enforce(settings, AI_ADMISSION_QUEUE_DEPTH="2", AI_ADMISSION_QUEUE_PER_USER="1")
    reader, other, third = scene["reader"], make_user("other@cit.edu"), make_user("third@cit.edu")

    def submit(user):
        conversation = Conversation.objects.create(user=user)
        with django_capture_on_commit_callbacks(execute=True):
            response = ask_stream(client_for(user), FLOOD_QUESTION, conversation_id=conversation.pk)
        if response.status_code == 200:
            response._iterator.close()
        return response

    assert submit(reader).status_code == 200
    refused = submit(reader)
    assert refused.status_code == 503 and refused["Retry-After"] == "5"
    assert refused.json() == {
        "detail": "IRIS is busy answering other questions. Please try again shortly.",
        "status": "busy", "reason": "user_queue_full",
    }
    assert submit(other).status_code == 200, "one asker cannot take every place"
    full = submit(third)
    assert (full.status_code, full.json()["reason"]) == (503, "queue_full")
    assert AskRun.objects.count() == len(dispatched) == 2, "a refusal queues nothing"


def test_unset_queue_limits_refuse_rather_than_guess(scene, settings, dispatched):
    enforce(settings, AI_ADMISSION_QUEUE_DEPTH="")
    response = ask_stream(scene["client"], FLOOD_QUESTION, conversation_id=scene["conversation"].pk)
    assert (response.status_code, response.json()["reason"]) == (503, "not_configured")
    assert not AskRun.objects.exists() and not dispatched


def test_local_fakes_incur_no_charges(embedder, space, client_for, dispatched, django_capture_on_commit_callbacks):
    from apps.ai.providers.fakes import ScriptedLLM

    reader = make_user("reader@cit.edu")
    make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    run_id, _ = durable_http._submit(
        client_for(reader), conversation, dispatched, django_capture_on_commit_callbacks
    )
    with use_composition_root(root_with(embedder=embedder, llm=ScriptedLLM())):
        answer_queued_question(run_id)
    assert AskRun.objects.get(pk=run_id).state == "succeeded"
    assert not _reservations().exists()


def test_the_reconnecting_stream_still_rechecks_ownership(scene, dispatched, client_for,
                                                           django_capture_on_commit_callbacks):
    run_id, _ = _answer(scene, dispatched, django_capture_on_commit_callbacks)
    stranger = client_for(make_user("stranger@cit.edu"))
    response = stranger.get(reverse("ai-ask-run-stream", args=[run_id]))
    assert response.status_code == 404


def test_a_refusal_that_only_degraded_retrieval_is_not_reported_busy(
    scene, dispatched, django_capture_on_commit_callbacks
):
    from apps.ai.admission import scope as admission_scope

    admitted = scene["root"]._llm

    class RerankWasRefused:
        """A refused rerank earlier in the run, then a generated answer."""

        def __getattr__(self, name):
            return getattr(admitted, name)

        def stream(self, system, user):
            admission_scope.note_denial("lane_busy")
            yield from admitted.stream(system, user)

    scene["root"]._llm = RerankWasRefused()
    _, frames = _answer(scene, dispatched, django_capture_on_commit_callbacks)
    assert frames[-1][1] == "done" and frames[-1][2]["mode"] != "unavailable"
    assert "capacity_limited" not in [frame[1] for frame in frames]
