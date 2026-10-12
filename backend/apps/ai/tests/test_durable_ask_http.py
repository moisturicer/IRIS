"""A queued question, through the HTTP boundary (IR-544, ADR-040).

The worker is `answer_queued_question` called directly -- what a Celery worker
runs -- and every vendor is a deterministic fake from `use_composition_root`.
Nothing here measures or claims real-provider throughput.

The story every test tells a piece of: a reader submits over `/ask/stream/`,
sees `run_queued`, leaves, comes back through `/ask/runs/<uuid>/stream/` and
receives the rest of the run -- including exactly one final Turn.
"""

import json
import uuid

import pytest
from django.urls import reverse

from apps.ai import durable
from apps.ai.composition import use_composition_root
from apps.ai.models import AskRun, AskRunEvent, Conversation, Turn
from apps.ai.providers.fakes import ScriptedLLM
from apps.ai.providers.ports import StreamDelta
from apps.ai.routing.chat import RoutingDecided
from apps.ai.tasks import answer_queued_question
from core.enums import PipelineStatus

from .corpus import FLOOD_QUESTION, FLOOD_TEXT, ask_stream, make_record, make_user, root_with

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def queued(settings):
    settings.AI_DURABLE_ASK = True
    settings.AI_DURABLE_ASK_POLL_SECONDS = 0
    return settings


@pytest.fixture
def dispatched(monkeypatch):
    """Run ids handed to Celery, instead of a broker."""
    sent = []
    monkeypatch.setattr(
        answer_queued_question, "apply_async", lambda args, **limits: sent.append((args[0], limits)),
    )
    return sent


def _frames(chunks) -> list[tuple[int, str, dict]]:
    """``(id, event, data)`` for each SSE record; comment lines skipped."""
    frames = []
    for block in b"".join(chunks).decode("utf-8").split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.strip().split("\n") if line and not line.startswith(":")
        )
        if "event" in fields:
            frames.append((int(fields["id"]), fields["event"], json.loads(fields["data"])))
    return frames


def _submit(client, conversation, dispatched, django_capture_on_commit_callbacks, **body):
    """Submit, read the first event, disconnect. Returns ``(run_id, frame)``."""
    with django_capture_on_commit_callbacks(execute=True):
        response = ask_stream(
            client, FLOOD_QUESTION, conversation_id=conversation.pk, **body
        )
    assert response.status_code == 200
    first = next(iter(response.streaming_content))
    # The browser leaves. The test client's own wrapper closes the stream with
    # `request_finished` held off, so the test's connection stays open.
    response._iterator.close()
    (frame,) = _frames([first])
    return frame[2]["run_id"], frame


def _follow(client, run_id, after=0, **headers):
    response = client.get(
        reverse("ai-ask-run-stream", args=[run_id]), {"after": after} if after else {}, **headers
    )
    return response, (_frames(response.streaming_content) if response.status_code == 200 else None)


@pytest.fixture
def scene(embedder, space, client_for):
    reader = make_user("reader@cit.edu")
    flood = make_record(title="Flood Prediction", text=FLOOD_TEXT, embedder=embedder, space=space)
    conversation = Conversation.objects.create(user=reader)
    llm = ScriptedLLM(stream_deltas=[
        StreamDelta(reasoning="private working "),
        StreamDelta(text="Rainfall gauges "),
        StreamDelta(text="feed the model [1]."),
    ])
    return {
        "reader": reader, "client": client_for(reader), "flood": flood,
        "conversation": conversation, "root": root_with(embedder=embedder, llm=llm),
    }


class QueuedQuestionTests:
    def test_submit_disconnect_reconnect_and_one_final_turn(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        client, conversation = scene["client"], scene["conversation"]
        run_id, (sequence, name, data) = _submit(
            client, conversation, dispatched, django_capture_on_commit_callbacks
        )

        assert (sequence, name, data["state"]) == (1, "run_queued", "queued")
        assert dispatched == [(run_id, {"soft_time_limit": 60, "time_limit": 75})], (
            "dispatched once, after the run committed, limited by its deadline"
        )
        run = AskRun.objects.get(pk=run_id)
        assert run.state == "queued" and run.user == scene["reader"]
        assert (run.deadline_at - run.created_at).total_seconds() == pytest.approx(30, abs=1)
        assert not Turn.objects.exists(), "leaving only unsubscribed; nothing ran yet"

        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)

        response, frames = _follow(client, run_id, after=1)
        assert response["Content-Type"].startswith("text/event-stream")
        assert [frame[1] for frame in frames] == [
            "run_started", "retrieval_started", "retrieval_finished", "generation_started",
            "text_delta", "text_delta", "citations_resolved", "done",
        ]
        assert [frame[0] for frame in frames] == list(range(2, 10))
        assert frames[0][2] == {"run_id": run_id, "state": "running", "attempt": 1}

        done = frames[-1][2]
        turn = Turn.objects.get()
        assert done["turn_id"] == turn.pk and done["conversation_id"] == conversation.pk
        assert done["answer"] == "Rainfall gauges feed the model [1]."
        assert [s["id"] for s in done["sources"]] == [scene["flood"].pk]

        # The same Turn a reopened conversation shows.
        reopened = client.get(reverse("ai-conversation-detail", args=[conversation.pk])).json()
        (stored,) = reopened["turns"]
        assert stored["id"] == turn.pk and stored["answer"] == done["answer"]
        assert stored["citations"] == done["citations"]

        run.refresh_from_db()
        assert (run.state, run.end_reason, run.turn_id) == ("succeeded", "generated", turn.pk)
        assert [a.state for a in run.attempts.all()] == ["finished"]

    def test_the_whole_journal_replays_from_the_start_or_a_last_event_id(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)

        _, everything = _follow(scene["client"], run_id)
        assert everything[0][1] == "run_queued" and everything[-1][1] == "done"
        _, tail = _follow(scene["client"], run_id, HTTP_LAST_EVENT_ID="7")
        assert tail == everything[7:]

    def test_a_redelivery_after_success_writes_nothing(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)
            events = AskRunEvent.objects.count()
            answer_queued_question(run_id)

        assert Turn.objects.count() == 1
        assert AskRunEvent.objects.count() == events

    def test_a_restarted_worker_fences_out_the_attempt_it_replaced(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        # The first worker starts, writes a little, and is lost.
        lost = durable.claim(run_id)
        durable.append(lost, "text_delta", {"text": "half an ans"})

        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)  # the redelivered message

        # The first worker waking up again can write nothing.
        with pytest.raises(durable.StaleAttempt):
            durable.append(lost, "text_delta", {"text": "wer"})
        with pytest.raises(durable.StaleAttempt):
            durable.finish_without_turn(lost, "failed", "error")

        assert Turn.objects.count() == 1
        run = AskRun.objects.get(pk=run_id)
        assert [a.state for a in run.attempts.all()] == ["superseded", "finished"]
        _, frames = _follow(scene["client"], run_id)
        started = [data["attempt"] for _, name, data in frames if name == "run_started"]
        assert started == [1, 2], "a client resets its partial text on the second start"
        assert [name for _, name, _ in frames].count("done") == 1

    def test_a_deleted_conversation_is_not_resurrected(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        client, conversation = scene["client"], scene["conversation"]
        run_id, _ = _submit(client, conversation, dispatched, django_capture_on_commit_callbacks)
        assert client.delete(reverse("ai-conversation-detail", args=[conversation.pk])).status_code == 204

        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)

        assert not Conversation.objects.filter(pk=conversation.pk).exists()
        assert not Turn.objects.exists() and not AskRun.objects.exists()

    def test_a_conversation_deleted_mid_answer_stays_deleted(
        self, scene, embedder, dispatched, django_capture_on_commit_callbacks
    ):
        conversation = scene["conversation"]

        class _DeletesMidAnswer(ScriptedLLM):
            def stream(self, system, user):
                yield StreamDelta(text="Rainfall ")
                Conversation.objects.filter(pk=conversation.pk).delete()
                yield StreamDelta(text="gauges [1].")

        run_id, _ = _submit(scene["client"], conversation, dispatched,
                            django_capture_on_commit_callbacks)
        with use_composition_root(root_with(embedder=embedder, llm=_DeletesMidAnswer())):
            answer_queued_question(run_id)

        assert not Conversation.objects.filter(pk=conversation.pk).exists()
        assert not Turn.objects.exists()

    def test_reasoning_never_enters_the_journal(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)

        assert not AskRunEvent.objects.filter(name="reasoning_delta").exists()
        stored = json.dumps(list(AskRunEvent.objects.values_list("data", flat=True)))
        assert "private working" not in stored
        _, frames = _follow(scene["client"], run_id)
        assert "reasoning" not in frames[-1][2]
        # IR-381's storage on the Turn is unchanged: no policy says stop.
        assert Turn.objects.get().reasoning == "private working "

    def test_replay_rechecks_what_the_reader_may_see_now(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)

        flood = scene["flood"]
        flood.pipeline_status = PipelineStatus.DRAFT
        flood.save(update_fields=["pipeline_status"])

        _, frames = _follow(scene["client"], run_id)
        by_name = {name: data for _, name, data in frames}
        assert by_name["citations_resolved"]["citations"] == []
        assert by_name["done"]["citations"] == [] and by_name["done"]["sources"] == []

    def test_someone_elses_run_is_indistinguishable_from_a_missing_one(
        self, scene, client_for, dispatched, django_capture_on_commit_callbacks
    ):
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        stranger = client_for(make_user("stranger@cit.edu"))

        foreign, _ = _follow(stranger, run_id)
        missing, _ = _follow(stranger, str(uuid.uuid4()))
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()

    def test_one_conversation_answers_one_question_at_a_time(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        client, conversation = scene["client"], scene["conversation"]
        run_id, _ = _submit(client, conversation, dispatched, django_capture_on_commit_callbacks)

        refused = ask_stream(client, FLOOD_QUESTION, conversation_id=conversation.pk)
        assert refused.status_code == 409
        assert AskRun.objects.count() == 1

        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)
        _submit(client, conversation, dispatched, django_capture_on_commit_callbacks)
        assert AskRun.objects.count() == 2

    def test_a_done_whose_turn_is_gone_still_ends_the_stream(
        self, scene, dispatched, django_capture_on_commit_callbacks
    ):
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)
        Turn.objects.all().delete()

        _, frames = _follow(scene["client"], run_id)
        assert frames[-1][1:] == (
            "run_failed", {"run_id": run_id, "state": "failed", "reason": "unavailable"},
        )

    def test_a_run_past_its_deadline_ends_without_an_answer(
        self, scene, queued, dispatched, django_capture_on_commit_callbacks
    ):
        queued.AI_DURABLE_ASK_DEADLINE_SECONDS = 0
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)
        with use_composition_root(scene["root"]):
            answer_queued_question(run_id)

        assert not Turn.objects.exists()
        _, frames = _follow(scene["client"], run_id)
        assert frames[-1][1:] == (
            "run_failed", {"run_id": run_id, "state": "expired", "reason": "deadline_exceeded"},
        )

    def test_a_run_no_worker_picks_up_is_expired_by_its_reader(
        self, scene, queued, dispatched, django_capture_on_commit_callbacks
    ):
        queued.AI_DURABLE_ASK_DEADLINE_SECONDS = 0
        queued.AI_DURABLE_ASK_STALE_SECONDS = 0
        run_id, _ = _submit(scene["client"], scene["conversation"], dispatched,
                            django_capture_on_commit_callbacks)

        _, frames = _follow(scene["client"], run_id)
        assert [name for _, name, _ in frames] == ["run_queued", "run_failed"]
        assert AskRun.objects.get(pk=run_id).state == "expired"


class NotQueuedTests:
    def test_with_the_switch_off_nothing_is_queued(self, scene, queued):
        queued.AI_DURABLE_ASK = False
        with use_composition_root(scene["root"]):
            response = ask_stream(scene["client"], FLOOD_QUESTION,
                                  conversation_id=scene["conversation"].pk)
            body = b"".join(response.streaming_content).decode()
        assert body.startswith("event: retrieval_started")
        assert not AskRun.objects.exists()

    def test_a_one_off_question_is_answered_in_the_request(self, scene):
        with use_composition_root(scene["root"]):
            response = ask_stream(scene["client"], FLOOD_QUESTION)
            body = b"".join(response.streaming_content).decode()
        assert "event: done" in body
        assert not AskRun.objects.exists()


def test_the_journal_keeps_routing_decisions_but_not_router_probabilities():
    routing = {
        "lane": "passage", "suggested_lane": "passage", "stage": "jev", "reason": "code",
        "injection_flagged": False, "planner_allowed": False, "override": None,
        "override_applied": False, "allowed_overrides": ["passage"],
        "probabilities": {"passage": 0.9},
    }
    public = durable.public_event(RoutingDecided(routing))
    assert "probabilities" not in public["routing"]
    assert public["routing"]["allowed_overrides"] == ["passage"]
