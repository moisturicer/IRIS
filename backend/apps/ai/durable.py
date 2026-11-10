"""Django's queued Ask IRIS questions, read-only since IR-957.

IR-544 (ADR-040) queued a question as an owned `AskRun` with a fenced worker
and a replayable journal. Django no longer answers (ADR-049 §27): the AI
runtime does. What stays is what a reader needs for the runs asked before the
switch:

- `follow` replays a run's public journal from a cursor, re-checking
  permissions on every read, exactly as before;
- `cancel` ends an unfinished run;
- `retire` ends a run nothing will answer now as `failed`, reason `retired`,
  with its one terminal event, so no follower waits on it.

Migration `0044_retire_django_ask_runs` retires every run still queued or
running when the switch is deployed.
"""

from __future__ import annotations

import json
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.ai import public as public_protocol
from apps.ai.models import AskRun, AskRunAttempt, AskRunEvent, Conversation, Turn
from apps.ai.models.queued import CANCELLED, EXPIRED, FAILED, PARTIAL, SUCCEEDED
from apps.ai.grants.reads import research_records

#: The routing fields a reader acts on. The router's per-lane probabilities
#: are a provider's output, not application activity, and stay out.
PUBLIC_ROUTING_FIELDS = (
    "lane", "suggested_lane", "stage", "reason", "injection_flagged", "planner_allowed",
    "override", "override_applied", "allowed_overrides",
)

#: A comment line every few seconds while nothing happens. Parsers skip it,
#: proxies see traffic, and a follower whose reader left notices on the write.
HEARTBEAT_SECONDS = 5.0

_BATCH = 100


def public_routing(routing: dict) -> dict:
    return {key: routing[key] for key in PUBLIC_ROUTING_FIELDS if key in routing}


def cancel(run_id, user):
    """End the asker's unfinished run as `cancelled`. Returns the run as it
    now stands -- already terminal, it is unchanged -- or ``None`` when it is
    not the asker's or is gone.

    Takes the Conversation's lock and then the run's, the order a finishing
    attempt takes, so a cancel and a final Turn cannot both commit."""
    with transaction.atomic():
        run = _lock_owned(run_id, user)
        if run is not None and not run.is_terminal:
            _end(run, CANCELLED, "cancelled", event=("run_cancelled", {
                "run_id": str(run.pk), "state": CANCELLED, "reason": "cancelled",
            }))
    return run


def _lock_owned(run_id, user):
    """``user``'s run, locked after its Conversation -- the order a finishing
    attempt takes -- or ``None`` when it is not theirs or is gone. Inside the
    caller's transaction."""
    conversation_id = (
        AskRun.objects.owned_by(user).filter(pk=run_id).values_list("conversation_id", flat=True).first()
    )
    if conversation_id is None:
        return None
    Conversation.objects.select_for_update().filter(pk=conversation_id).first()
    return AskRun.objects.owned_by(user).select_for_update().filter(pk=run_id).first()


def latest_run_for_reader(conversation):
    """The Conversation's latest run while it has no Turn to show for it:
    unfinished, or ended without an answer. ``None`` once its Turn is in the
    transcript, or once a later Turn answered the Conversation anyway -- an
    old stopped run is then history, not something to retry. What a reader
    opening the Conversation needs to follow the run again, or to see that it
    stopped and retry it."""
    run = conversation.ask_runs.order_by("-created_at").first()
    if run is None or run.state in (SUCCEEDED, PARTIAL):
        return None
    if run.is_terminal and conversation.turns.filter(created_at__gt=run.created_at).exists():
        return None
    return {
        "id": str(run.pk),
        "state": run.state,
        "end_reason": run.end_reason,
        "question": run.request.get("question", ""),
        "retry_of": str(run.retry_of_id) if run.retry_of_id else None,
        "last_sequence": run.last_sequence,
    }


def _append(run: AskRun, attempt, name: str, data: dict) -> None:
    """Add one event to a run this transaction has locked or just created."""
    run.last_sequence += 1
    AskRun.objects.filter(pk=run.pk).update(last_sequence=run.last_sequence)
    AskRunEvent.objects.create(
        run=run, sequence=run.last_sequence, name=name, data=data, attempt=attempt,
    )


def _end(run: AskRun, state: str, reason: str, *, attempt=None, turn=None, event=None) -> None:
    """Make ``run`` terminal and journal its one terminal event. Locked caller."""
    now = timezone.now()
    if run.current_attempt_id is not None:
        AskRunAttempt.objects.filter(pk=run.current_attempt_id).update(
            state=AskRunAttempt.FINISHED, finished_at=now,
        )
    run.state, run.end_reason, run.finished_at = state, reason, now
    run.current_attempt, run.turn = None, turn
    run.save(update_fields=["state", "end_reason", "finished_at", "current_attempt", "turn"])
    name, data = event or ("run_failed", {"run_id": str(run.pk), "state": state, "reason": reason})
    _append(run, attempt, name, data)


RETIRED = "retired"


def retire(run_id) -> None:
    """End a run Django will never answer now (IR-957). A terminal run is left alone."""
    with transaction.atomic():
        run = AskRun.objects.select_for_update().filter(pk=run_id).first()
        if run is not None and not run.is_terminal:
            _end(run, FAILED, RETIRED)


def _expire_overdue(run: AskRun) -> bool:
    """End a locked run nobody is finishing -- its dispatch was lost, or every
    worker that took it died -- fencing out any attempt that later wakes.
    True when the run is (now) over."""
    if run.is_terminal:
        return True
    if timezone.now() < run.deadline_at + timedelta(seconds=settings.AI_DURABLE_ASK_STALE_SECONDS):
        return False
    _end(run, EXPIRED, "deadline_exceeded")
    return True


def expire_if_overdue(run_id) -> None:
    with transaction.atomic():
        run = AskRun.objects.select_for_update().filter(pk=run_id).first()
        if run is not None:
            _expire_overdue(run)


def follow(run_id, user, after: int = 0, *, public=False, sleep=time.sleep, clock=time.monotonic):
    """SSE frames for every event after ``after``, then the live tail, until
    the run's terminal event has been sent. Ends quietly if the run stops
    being the reader's -- deleted with its Conversation, for instance.

    ``public`` (IR-595) sends the `apps.ai.public` protocol instead.

    Reads only. Closing this generator touches nothing in the run.
    """
    cursor = after
    projector = public_protocol.StreamProjector(_seed_activity(run_id, after)) if public else None
    last_sent = clock()
    while True:
        run = AskRun.objects.owned_by(user).filter(pk=run_id).first()
        if run is None:
            return
        batch = list(run.events.filter(sequence__gt=cursor).order_by("sequence")[:_BATCH])
        for event in batch:
            cursor = event.sequence
            if projector is None:
                yield _frame(event, user)
            else:
                yield from _public_frames(event, user, projector)
            last_sent = clock()
        if batch:
            continue
        if run.is_terminal:
            return
        grace = timedelta(seconds=settings.AI_DURABLE_ASK_STALE_SECONDS)
        if timezone.now() >= run.deadline_at + grace:
            expire_if_overdue(run.pk)
            continue
        if clock() - last_sent >= HEARTBEAT_SECONDS:
            yield ": keepalive\n\n"
            last_sent = clock()
        sleep(settings.AI_DURABLE_ASK_POLL_SECONDS)


def _seed_activity(run_id, after: int):
    """The activity a reader reconnecting after ``after`` already holds."""
    if after <= 0:
        return None
    names = AskRunEvent.objects.filter(run_id=run_id, sequence__lte=after).order_by(
        "-sequence").values_list("name", flat=True)
    return next((s for s in map(public_protocol.activity_state, names) if s), None)


def _public_frames(event: AskRunEvent, user, projector):
    """Public frames for one journal event. Only the last carries the event's
    `id:`, so a reader who dropped between two frames replays both."""
    name, data = _payload(event, user, public=True)
    frames = projector.feed(name, data)
    for position, (frame_name, frame_data) in enumerate(frames):
        if position == len(frames) - 1:
            yield _sse(event.sequence, frame_name, frame_data)
        else:
            yield f"event: {frame_name}\ndata: {json.dumps(frame_data)}\n\n"


def _frame(event: AskRunEvent, user):
    name, data = _payload(event, user)
    return _sse(event.sequence, name, data)


def _payload(event: AskRunEvent, user, *, public=False):
    data = event.data
    if event.name == "citations_resolved":
        visible = _visible_ids(user, [c["record_id"] for c in data["citations"]])
        data = {"citations": [c for c in data["citations"] if c["record_id"] in visible]}
    elif event.name in ("candidates_selected", "candidates_updated"):
        data = _visible_candidates(user, data)
    elif event.name == "done":
        data = done_for_reader(event, user, public=public)
        if data is None:
            # The Turn is gone; the run is still over, and must say so.
            return "run_failed", {
                "run_id": str(event.run_id), "state": FAILED, "reason": "unavailable",
            }
    return event.name, data


def _sse(sequence: int, name: str, data: dict) -> str:
    return f"id: {sequence}\nevent: {name}\ndata: {json.dumps(data)}\n\n"


def _visible_ids(user, ids) -> set:
    return set(research_records(user).filter(pk__in=set(ids)).values_list("pk", flat=True))


def _visible_candidates(user, data: dict) -> dict:
    """A candidate event as it reads now: only Records the reader may see, and
    their current titles. One that is not visible is simply absent (IR-546)."""
    rows = data["candidates"]
    titles = dict(
        research_records(user)
        .filter(pk__in={row["record_id"] for row in rows}).values_list("pk", "title")
    )
    return {**data, "candidates": [
        {**row, **({"title": titles[row["record_id"]]} if "title" in row else {})}
        for row in rows if row["record_id"] in titles
    ]}


def done_for_reader(event: AskRunEvent, user, *, public=False):
    """The final answer as it reads now: rebuilt from the Turn, never replayed."""
    from apps.ai.conversations import turn_for_reader

    turn = Turn.objects.filter(pk=event.data["turn_id"], conversation__user=user).first()
    if turn is None:
        return None
    reader = turn_for_reader(turn, user, public=public)
    sources = event.data.get("sources", [])
    if turn.comparison and "comparison" not in reader:
        sources = []
    visible = _visible_ids(user, [source["id"] for source in sources])
    body = {
        key: value
        for key, value in reader.items()
        # `reasoning` is private; `created_at` and `question` are not part of `done`.
        if key not in ("id", "question", "created_at", "reasoning", "state")
    }
    if "routing" in body:
        body["routing"] = public_routing(body["routing"])
    body.update(
        turn_id=turn.pk,
        conversation_id=turn.conversation_id,
        mode=reader.get("state", reader.get("mode")),
        sources=[source for source in sources if source["id"] in visible],
    )
    return body
