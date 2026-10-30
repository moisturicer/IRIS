"""IR-561: concurrent opens and sends use database identities, never mount order."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from django.db import close_old_connections
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ai.composition import use_composition_root
from apps.ai.models import Conversation, Turn
from apps.ai.providers.fakes import ScriptedLLM
from apps.records.models import Record
from core.enums import PipelineStatus

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, make_record, make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]


def client(user):
    result = APIClient()
    result.force_authenticate(user)
    return result


@pytest.mark.parametrize("legacy", [False, True])
def test_concurrent_default_opens_adopt_history_and_allow_extra_conversations(legacy):
    user = make_user("identity@cit.edu")
    record = Record.objects.create(title="Paper", pipeline_status=PipelineStatus.PUBLISHED)
    original = Conversation.objects.create(user=user, record=record, title="Existing enquiry") if legacy else None
    barrier = Barrier(2)

    def open_chat():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            response = client(user).post(reverse("ai-conversations"),
                {"record": record.pk, "reuse_default": True}, format="json")
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: open_chat(), range(2)))
    assert all(code in (200, 201) for code, _ in results)
    default_id = results[0][1]["id"]
    assert {body["id"] for _, body in results} == {default_id}
    if original is not None:
        assert default_id == original.pk
    assert Conversation.objects.filter(user=user, record=record).count() == 1
    extra = client(user).post(reverse("ai-conversations"), {"record": record.pk}, format="json")
    assert extra.status_code == 201
    assert extra.json()["id"] != default_id
    listed = client(user).get(reverse("ai-conversations"), {"record": record.pk, "default": "true"})
    assert [row["id"] for row in listed.json()] == [default_id]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("public", [False, True])
def test_repeated_send_replays_one_turn_and_one_generation(embedder, space, stream, public):
    user = make_user("identity@cit.edu")
    record = make_record(title="Flood", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=user, record=record)
    llm = ScriptedLLM()
    body = {"question": FLOOD_QUESTION, "conversation_id": conversation.pk, "request_id": str(uuid4())}
    url = reverse("ai-ask-stream" if stream else "ai-ask")

    def send():
        response = client(user).post(url, body, format="json", **({"HTTP_X_IRIS_PROTOCOL": "public-1"} if public else {}))
        assert response.status_code == 200
        return b"".join(response.streaming_content).decode() if stream else response.json()

    with use_composition_root(root_with(embedder=embedder, llm=llm)):
        first, second = send(), send()
    turn = Turn.objects.get(conversation=conversation)
    assert len(llm.calls) == 1
    if stream:
        assert f'"turn_id": {turn.pk}' in first
        assert f'"turn_id": {turn.pk}' in second
    else:
        assert first["turn_id"] == second["turn_id"] == turn.pk
        assert first["answer"] == second["answer"]
        assert first["sources"] == second["sources"]


def test_concurrent_send_claims_before_vendor_call(embedder, space):
    user = make_user("identity@cit.edu")
    record = make_record(title="Flood", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=user, record=record)
    entered, release = Event(), Event()

    class HeldLLM(ScriptedLLM):
        def generate(self, system, user):
            entered.set()
            assert release.wait(timeout=15)
            return super().generate(system, user)

    llm = HeldLLM()
    root = root_with(embedder=embedder, llm=llm)
    body = {"question": FLOOD_QUESTION, "conversation_id": conversation.pk, "request_id": str(uuid4())}

    def send():
        close_old_connections()
        try:
            with use_composition_root(root):
                return client(user).post(reverse("ai-ask"), body, format="json")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(send)
        try:
            assert entered.wait(timeout=10)
            duplicate = send()
            assert duplicate.status_code == 409
            assert duplicate.json()["status"] == "pending"
        finally:
            release.set()
        original = first.result(timeout=15)
    replay = send()
    assert original.status_code == replay.status_code == 200
    assert original.json()["turn_id"] == replay.json()["turn_id"]
    assert Turn.objects.filter(conversation=conversation).count() == 1
    assert len(llm.calls) == 1


def test_request_identity_cannot_be_reused_for_different_input(embedder, space):
    user = make_user("identity@cit.edu")
    conversation = Conversation.objects.create(user=user)
    body = {"question": "No corpus", "conversation_id": conversation.pk, "request_id": str(uuid4())}
    with use_composition_root(root_with(embedder=embedder)):
        assert client(user).post(reverse("ai-ask"), body, format="json").status_code == 200
        response = client(user).post(reverse("ai-ask"), {**body, "widen": True}, format="json")
    assert response.status_code == 409
    other = make_user("other-identity@cit.edu")
    assert client(other).post(reverse("ai-ask"), body, format="json").status_code == 404


@pytest.mark.parametrize("request_id", ["", "not-a-uuid", 12])
def test_invalid_request_identity_is_refused(request_id):
    user = make_user("identity@cit.edu")
    conversation = Conversation.objects.create(user=user)
    response = client(user).post(reverse("ai-ask"), {
        "question": "Question", "conversation_id": conversation.pk, "request_id": request_id,
    }, format="json")
    assert response.status_code == 400
    assert not Turn.objects.exists()


def test_default_is_owned_and_restricted_records_cannot_be_named():
    user, other = make_user("identity@cit.edu"), make_user("other@cit.edu")
    record = Record.objects.create(title="Paper", pipeline_status=PipelineStatus.PUBLISHED)
    body = {"record": record.pk, "reuse_default": True}
    first = client(user).post(reverse("ai-conversations"), body, format="json")
    second = client(other).post(reverse("ai-conversations"), body, format="json")
    assert first.json()["id"] != second.json()["id"]
    hidden = Record.objects.create(title="Private")
    hidden_response = client(user).post(reverse("ai-conversations"), {**body, "record": hidden.pk}, format="json")
    missing_response = client(user).post(reverse("ai-conversations"), {**body, "record": hidden.pk + 10000}, format="json")
    assert hidden_response.status_code == missing_response.status_code == 400
    assert str(hidden_response.json()).replace(str(hidden.pk), "<id>") == str(missing_response.json()).replace(str(hidden.pk + 10000), "<id>")


def test_partial_stream_retry_does_not_generate_again(embedder, space):
    from .corpus import _CutOffLLM

    user = make_user("identity@cit.edu")
    record = make_record(title="Flood", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=user, record=record)
    body = {"question": FLOOD_QUESTION, "conversation_id": conversation.pk, "request_id": str(uuid4())}
    with use_composition_root(root_with(embedder=embedder, llm=_CutOffLLM())):
        first = client(user).post(reverse("ai-ask-stream"), body, format="json")
        with pytest.raises(RuntimeError, match="connection reset"):
            b"".join(first.streaming_content)
        second = client(user).post(reverse("ai-ask-stream"), body, format="json")
        replay = b"".join(second.streaming_content).decode()
    turn = Turn.objects.get(conversation=conversation)
    assert turn.state == "partial"
    assert f'"turn_id": {turn.pk}' in replay
    assert '"partial": true' in replay
