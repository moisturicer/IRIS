"""Queued questions: one owned run, a fenced worker, a replayable journal.

IR-544, ADR-040. With `AI_DURABLE_ASK` on, a question asked over the
existing `/ask/stream/` inside a Conversation is not answered inside the
request. Instead IRIS:

1. creates an `AskRun` and its first journal event (`run_queued`) in one
   transaction, and dispatches `answer_queued_question` only after it commits;
2. streams the run's journal back over the same SSE response -- the response
   *follows* the run and does not own it, so a disconnect unsubscribes and the
   answer carries on;
3. lets the reader reconnect with `GET /ask/runs/<uuid>/stream/?after=N` and
   receive every public event after ``N``, then the live tail, then one
   terminal event.

**Fencing.** Every worker delivery claims a new `AskRunAttempt` and becomes
`AskRun.current_attempt`. Every write -- a journal event, the final Turn --
locks the run row and checks it still names that attempt, so a superseded
attempt (a redelivered message whose first worker is still alive) cannot
append or finish anything. A terminal run accepts no claim at all, which is
why a redelivery after success writes no second Turn.

**What the journal holds.** Public events only: the run's own lifecycle,
routing without the router's probabilities, planner steps (code-owned names
and counts), retrieval counts, answer text and citations. Never a reasoning
delta, and the replayed `done` carries no reasoning either. `Turn.reasoning`
is still written as IR-381 decided; stopping that needs a recorded policy,
which this ticket does not have.

**Permissions are re-checked on every read.** Subscription and replay go
through `AskRun.objects.owned_by(user)`, so someone else's run is a 404 like a
missing one. Citations in a replayed `citations_resolved` are filtered to the
Records the reader may see now, and the `done` event is rebuilt from the
stored Turn by `turn_for_reader` on every replay -- the same re-resolution a
reopened transcript gets.

**One run at a time per Conversation.** A question asked while an earlier one
is unfinished is refused (409) rather than answered against a history that
lacks the earlier Turn.

**Off by default** (`AI_DURABLE_ASK`). Queue sizing, fairness and shared
spend limits are IR-545's and are not built here.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import closing, contextmanager
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.ai.answers.citations import PARTIAL as PARTIAL_ANSWER
from apps.ai.answers.events import Done, ReasoningDelta
from apps.ai.models import (
    AskRun,
    AskRunAttempt,
    AskRunEvent,
    Conversation,
    ResearchRun,
    Turn,
)
from apps.ai.models.queued import EXPIRED, FAILED, PARTIAL, QUEUED, RUNNING, SUCCEEDED
from apps.ai.orchestrator import ChatOrchestrator
from apps.records.models import Record

logger = logging.getLogger(__name__)

#: The request fields a worker needs to prepare the question again.
REQUEST_FIELDS = (
    "question", "conversation_id", "top_k", "widen", "route_override", "route_override_turn_id",
)

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


class StaleAttempt(Exception):
    """This attempt no longer owns the run: superseded, finished or deleted."""


def enabled() -> bool:
    return settings.AI_DURABLE_ASK


def requested(data) -> bool:
    """With the switch on, every question asked inside a Conversation is
    queued: its Turn has somewhere to live. A one-off question is answered in
    the request. No client flag -- a client that ignores the new events still
    reads the same stream to the same `done`."""
    return enabled() and data.get("conversation_id") not in (None, "")


def public_routing(routing: dict) -> dict:
    return {key: routing[key] for key in PUBLIC_ROUTING_FIELDS if key in routing}


# ---- submission -------------------------------------------------------------


def submit(prepared, user, data, *, max_sources: int):
    """Create the run and its `run_queued` event; dispatch once committed.

    ``None`` while an earlier run in the same Conversation is unfinished: a
    second worker would prepare its question without the first one's Turn in
    its history, and could write its Turn first.
    """
    request = {key: data[key] for key in REQUEST_FIELDS if key in data}
    request.update(conversation_id=prepared.conversation.pk, top_k=max_sources)
    deadline = timezone.now() + timedelta(seconds=settings.AI_DURABLE_ASK_DEADLINE_SECONDS)
    with transaction.atomic():
        # The Conversation, then its runs: the order finishing a run takes.
        Conversation.objects.select_for_update().filter(pk=prepared.conversation.pk).first()
        busy = AskRun.objects.select_for_update().filter(
            conversation=prepared.conversation, state__in=(QUEUED, RUNNING),
        )
        if any(not _expire_overdue(run) for run in busy):
            return None
        run = AskRun.objects.create(
            user=user, conversation=prepared.conversation, request=request, deadline_at=deadline,
        )
        _append(run, None, "run_queued", {
            "run_id": str(run.pk), "state": QUEUED, "deadline_at": deadline.isoformat(),
        })
        transaction.on_commit(lambda: _dispatch(run.pk))
    return run


def _dispatch(run_id) -> None:
    from apps.ai.tasks import answer_queued_question

    # Celery stops the worker where the reader-side expiry would have fenced
    # it anyway, so a stalled vendor call holds a `default` worker no longer.
    limit = settings.AI_DURABLE_ASK_DEADLINE_SECONDS + settings.AI_DURABLE_ASK_STALE_SECONDS
    try:
        answer_queued_question.apply_async(
            args=[str(run_id)], soft_time_limit=limit, time_limit=limit + 15,
        )
    except Exception:
        # The run stays queued; the first reader to look after its deadline
        # expires it (`expire_if_overdue`), so nobody waits forever.
        logger.exception("Could not dispatch queued question %s", run_id)


# ---- fenced writes ----------------------------------------------------------


def _append(run: AskRun, attempt, name: str, data: dict) -> None:
    """Add one event to a run this transaction has locked or just created."""
    run.last_sequence += 1
    AskRun.objects.filter(pk=run.pk).update(last_sequence=run.last_sequence)
    AskRunEvent.objects.create(
        run=run, sequence=run.last_sequence, name=name, data=data, attempt=attempt,
    )


def _locked(attempt: AskRunAttempt) -> AskRun:
    """The run, locked, if ``attempt`` still owns it; otherwise `StaleAttempt`."""
    run = AskRun.objects.select_for_update().filter(pk=attempt.run_id).first()
    if run is None or run.is_terminal or run.current_attempt_id != attempt.pk:
        raise StaleAttempt(str(attempt.pk))
    return run


def append(attempt: AskRunAttempt, name: str, data: dict) -> None:
    with transaction.atomic():
        _append(_locked(attempt), attempt, name, data)


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


def finish_without_turn(attempt: AskRunAttempt, state: str, reason: str) -> None:
    with transaction.atomic():
        _end(_locked(attempt), state, reason, attempt=attempt)


def claim(run_id):
    """Start a new attempt, superseding any earlier one, or return ``None``
    when there is nothing to do: the run is gone, finished, or past its
    original deadline (which this claim then records)."""
    with transaction.atomic():
        run = AskRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.is_terminal:
            return None
        if timezone.now() >= run.deadline_at:
            _end(run, EXPIRED, "deadline_exceeded")
            return None
        if run.current_attempt_id is not None:
            AskRunAttempt.objects.filter(pk=run.current_attempt_id).update(
                state=AskRunAttempt.SUPERSEDED, finished_at=timezone.now(),
            )
        attempt = AskRunAttempt.objects.create(run=run, number=run.attempts.count() + 1)
        run.current_attempt, run.state = attempt, RUNNING
        run.save(update_fields=["current_attempt", "state"])
        _append(run, attempt, "run_started", {
            "run_id": str(run.pk), "state": RUNNING, "attempt": attempt.number,
        })
    return attempt


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


# ---- the worker -------------------------------------------------------------


class _QueuedOrchestrator(ChatOrchestrator):
    """The chat orchestrator, writing its Turn only while its attempt owns the run."""

    def __init__(self, asked, *, max_sources, attempt):
        super().__init__(asked, max_sources=max_sources)
        self._attempt = attempt
        self.finished = False

    def _record_guard(self, answer):
        return self._finishing(answer)

    @contextmanager
    def _finishing(self, answer):
        with transaction.atomic():
            # The Conversation first, in the order its deletion takes it
            # (`ConversationDetailView.perform_destroy`): a Turn is either
            # written before the delete reads the rows it removes, or not at
            # all. Never after, which would bring a deleted transcript back.
            alive = Conversation.objects.select_for_update().filter(
                pk=self._asked.conversation.pk
            ).values_list("pk", flat=True)
            if not list(alive):
                raise StaleAttempt(str(self._attempt.pk))
            run = _locked(self._attempt)

            def written(turn: Turn) -> None:
                research_id = (self._routing.research or {}).get("run_id")
                if research_id and ResearchRun.objects.filter(pk=research_id).exists():
                    AskRunAttempt.objects.filter(pk=self._attempt.pk).update(
                        research_run_id=research_id,
                    )
                from apps.ai.presentation import record_sources

                _end(
                    run,
                    PARTIAL if answer.state == PARTIAL_ANSWER else SUCCEEDED,
                    answer.state,
                    attempt=self._attempt,
                    turn=turn,
                    event=("done", {"turn_id": turn.pk, "sources": record_sources(answer.sources)}),
                )
                self.finished = True

            yield written


def public_event(event):
    """What the journal stores for one answer event, or ``None`` to keep it out."""
    from apps.ai.routing.chat import RoutingDecided
    from apps.ai.views.chatbot import event_payload

    if isinstance(event, (Done, ReasoningDelta)):
        return None
    data = event_payload(event)
    if isinstance(event, RoutingDecided):
        data = {"routing": public_routing(data["routing"])}
    return data


def execute(run_id) -> None:
    """One delivery of `answer_queued_question`. Safe to run any number of times."""
    attempt = claim(run_id)
    if attempt is None:
        return
    try:
        _answer(attempt)
    except StaleAttempt:
        logger.info("Queued question %s: attempt %s was fenced out", run_id, attempt.pk)
    except Exception:
        # Celery's soft time limit lands here too, as a deadline overrun.
        logger.exception("Queued question %s failed", run_id)
        overdue = timezone.now() >= attempt.run.deadline_at
        try:
            finish_without_turn(
                attempt, EXPIRED if overdue else FAILED, "deadline_exceeded" if overdue else "error",
            )
        except StaleAttempt:
            pass


def _answer(attempt: AskRunAttempt) -> None:
    from django.http import Http404

    from apps.ai.views.chatbot import prepare_ask

    run = AskRun.objects.select_related("user").filter(pk=attempt.run_id).first()
    if run is None:
        raise StaleAttempt(str(attempt.pk))
    # Prepared again, as the asker, now: the Conversation and any override
    # Turn must still be theirs, and the resolver runs here, not in the request.
    try:
        prepared, error = prepare_ask(run.request, run.user)
    except Http404:
        prepared, error = None, True
    if error is not None:
        finish_without_turn(attempt, FAILED, "not_answerable")
        return

    orchestrator = _QueuedOrchestrator(
        prepared, max_sources=run.request["top_k"], attempt=attempt,
    )
    overdue = False
    events = orchestrator.answer_stream(run.user)
    # Closing records whatever answer text arrived as a `partial` Turn (IR-328).
    with closing(events):
        for event in events:
            if timezone.now() >= run.deadline_at and not orchestrator.finished:
                overdue = True
                break
            data = public_event(event)
            if data is not None:
                append(attempt, event.name, data)
    if not orchestrator.finished:
        if overdue:
            finish_without_turn(attempt, EXPIRED, "deadline_exceeded")
        else:
            finish_without_turn(attempt, FAILED, "no_answer")


# ---- following and replay ---------------------------------------------------


def follow(run_id, user, after: int = 0, *, sleep=time.sleep, clock=time.monotonic):
    """SSE frames for every event after ``after``, then the live tail, until
    the run's terminal event has been sent. Ends quietly if the run stops
    being the reader's -- deleted with its Conversation, for instance.

    Reads only. Closing this generator touches nothing in the run.
    """
    cursor = after
    last_sent = clock()
    while True:
        run = AskRun.objects.owned_by(user).filter(pk=run_id).first()
        if run is None:
            return
        batch = list(run.events.filter(sequence__gt=cursor).order_by("sequence")[:_BATCH])
        for event in batch:
            cursor = event.sequence
            yield _frame(event, user)
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


def _frame(event: AskRunEvent, user):
    data = event.data
    if event.name == "citations_resolved":
        visible = _visible_ids(user, [c["record_id"] for c in data["citations"]])
        data = {"citations": [c for c in data["citations"] if c["record_id"] in visible]}
    elif event.name == "done":
        data = _done(event, user)
        if data is None:
            # The Turn is gone; the run is still over, and must say so.
            return _sse(event.sequence, "run_failed", {
                "run_id": str(event.run_id), "state": FAILED, "reason": "unavailable",
            })
    return _sse(event.sequence, event.name, data)


def _sse(sequence: int, name: str, data: dict) -> str:
    return f"id: {sequence}\nevent: {name}\ndata: {json.dumps(data)}\n\n"


def _visible_ids(user, ids) -> set:
    return set(Record.objects.visible_to(user).filter(pk__in=set(ids)).values_list("pk", flat=True))


def _done(event: AskRunEvent, user):
    """The final answer as it reads now: rebuilt from the Turn, never replayed."""
    from apps.ai.conversations import turn_for_reader

    turn = Turn.objects.filter(pk=event.data["turn_id"], conversation__user=user).first()
    if turn is None:
        return None
    reader = turn_for_reader(turn, user)
    sources = event.data.get("sources", [])
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
        mode=reader["state"],
        sources=[source for source in sources if source["id"] in visible],
    )
    return body
