"""Django no longer answers reader questions (IR-957, ADR-049 §27).

The AI runtime answers Ask IRIS and Paper Chat. These pin the switch from
Django's side: the old answer routes refuse with 410 and touch nothing, a
question Django was still answering ends with an explicit state, and a
Conversation Django answered stays readable to its owner and no one else.
"""

from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from apps.ai.answers.citations import GENERATED
from apps.ai.models import AskRun, AskRunEvent, Conversation, Turn
from apps.ai.models.queued import FAILED, QUEUED, RUNNING, SUCCEEDED
from apps.ai.tasks import answer_queued_question

from .corpus import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

retire_migration = import_module("apps.ai.migrations.0044_retire_django_ask_runs")


@pytest.fixture
def reader():
    return make_user("retired-path@cit.edu")


def _run(conversation, state, **fields):
    return AskRun.objects.create(
        user=conversation.user, conversation=conversation, state=state,
        request={"question": "Which gauges?"},
        deadline_at=timezone.now() + timedelta(minutes=5), **fields,
    )


ANSWER_ROUTES = [
    ("post", lambda: reverse("ai-ask"), {"question": "Which gauges?"}),
    ("post", lambda: reverse("ai-ask-stream"), {"question": "Which gauges?"}),
    ("post", lambda: reverse("ai-search"), {"query": "gauges"}),
]


@pytest.mark.parametrize("method, url, body", ANSWER_ROUTES)
def test_the_old_answer_routes_are_gone_and_write_nothing(method, url, body, reader, client_for):
    conversation = Conversation.objects.create(user=reader)

    response = getattr(client_for(reader), method)(
        url(), {**body, "conversation_id": conversation.pk}, format="json")

    assert response.status_code == 410
    assert response.json()["status"] == "retired"
    assert not Turn.objects.exists()
    assert not AskRun.objects.exists()


def test_a_retry_of_an_old_run_starts_nothing(reader, client_for):
    run = _run(Conversation.objects.create(user=reader), FAILED)

    response = client_for(reader).post(reverse("ai-ask-run-retry", args=[run.pk]))

    assert response.status_code == 410
    assert AskRun.objects.count() == 1


@pytest.mark.parametrize("method, url, body", ANSWER_ROUTES)
def test_the_old_answer_routes_still_need_a_session(method, url, body, client):
    assert getattr(client, method)(url(), body, content_type="application/json").status_code == 401


def test_no_new_django_conversation_can_be_started(reader, client_for):
    response = client_for(reader).post(reverse("ai-conversations"), {}, format="json")

    assert response.status_code == 405
    assert not Conversation.objects.exists()


def test_a_django_conversation_stays_readable_to_its_owner_alone(reader, client_for):
    conversation = Conversation.objects.create(user=reader, title="Gauges")
    Turn.objects.create(conversation=conversation, question="Which gauges?",
                        answer="Rain gauges.", state=GENERATED)
    detail = reverse("ai-conversation-detail", args=[conversation.pk])

    listed = client_for(reader).get(reverse("ai-conversations"))
    opened = client_for(reader).get(detail)
    stranger = client_for(make_user("stranger@cit.edu")).get(detail)

    assert [c["id"] for c in listed.json()] == [conversation.pk]
    assert opened.status_code == 200
    assert opened.json()["turns"][0]["answer"] == "Rain gauges."
    assert stranger.status_code == 404


def test_the_switch_ends_every_question_django_was_answering(reader):
    conversation = Conversation.objects.create(user=reader)
    queued, running = _run(conversation, QUEUED), _run(conversation, RUNNING, last_sequence=3)
    done = _run(conversation, SUCCEEDED, end_reason="answered")

    retire_migration.retire_open_runs(django_apps, None)

    for run in (queued, running):
        run.refresh_from_db()
        assert (run.state, run.end_reason, run.current_attempt_id) == (FAILED, "retired", None)
        event = AskRunEvent.objects.get(run=run, sequence=run.last_sequence)
        assert event.name == "run_failed"
        assert event.data == {"run_id": str(run.pk), "state": FAILED, "reason": "retired"}
    assert running.last_sequence == 4
    done.refresh_from_db()
    assert (done.state, done.end_reason) == (SUCCEEDED, "answered")
    assert not AskRunEvent.objects.filter(run=done).exists()


def test_a_message_dispatched_before_the_switch_ends_its_run_unanswered(reader):
    conversation = Conversation.objects.create(user=reader)
    run, done = _run(conversation, QUEUED), _run(conversation, SUCCEEDED)

    answer_queued_question(str(run.pk))
    answer_queued_question(str(done.pk))

    run.refresh_from_db(); done.refresh_from_db()
    assert (run.state, run.end_reason) == (FAILED, "retired")
    assert done.state == SUCCEEDED
    assert not Turn.objects.exists()


def test_a_reader_following_a_retired_run_reaches_its_end(reader, client_for):
    run = _run(Conversation.objects.create(user=reader), QUEUED)
    retire_migration.retire_open_runs(django_apps, None)

    response = client_for(reader).get(reverse("ai-ask-run-stream", args=[run.pk]))
    body = b"".join(response.streaming_content).decode()

    assert "event: run_failed" in body
    assert '"reason": "retired"' in body
