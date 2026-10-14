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

**Cancel and retry (IR-548).** The asker may cancel an unfinished run. That
commits its one terminal state, `cancelled`, under the same locks a finishing
attempt takes, so whichever commits first wins and the other is refused.
After it the attempt can write nothing -- no event, no Turn, partial or
whole -- and its run scope admits no new provider attempt. A call already
sent is left to finish and is charged. A run that ended without its answer
may be retried: a new run linked by `retry_of`, with its own deadline, its
own per-run caps and the queue admission any new question meets. It is not a
redelivery. Asking to retry the same run again returns the first retry.

**Off by default** (`AI_DURABLE_ASK`), and Django refuses to start with it on
unless provider admission is enforced (IR-545, ADR-041).

**Bounded and fair (IR-545).** A submission is admitted to the queue only
while fewer than `AI_ADMISSION_QUEUE_DEPTH` questions are unfinished, and
fewer than `AI_ADMISSION_QUEUE_PER_USER` of them are the asker's -- so one
reader cannot fill it. Otherwise it is refused as busy, before anything is
created or dispatched. The check and the insert are serialised across every
process by a transaction-scoped advisory lock.

**One deadline (IR-545).** Every vendor call a worker makes is bounded by the
time left until the run's original `deadline_at`; a retry, a fallback or a
redelivery never restarts it. Each provider attempt is admitted against the
run's own caps (`ask:<run id>`) as well as the shared ones, and a run that met
a refusal that cost it its answer journals `capacity_limited` before its
terminal event, so the journal records *busy* rather than a silent gap. The
answer itself is the explicit unavailable state; no client renders this event
yet.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import closing, contextmanager
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.utils import timezone

from apps.ai.admission import scope as admission_scope

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
from apps.ai.models.queued import (
    CANCELLED, EXPIRED, FAILED, PARTIAL, QUEUED, RETRYABLE_STATES, RUNNING, SUCCEEDED,
)
from apps.ai.orchestrator import ChatOrchestrator
from apps.ai.providers.deadline import model_call_deadline
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


class NotRetryable(Exception):
    """The run has not ended, or ended with its answer. ``state`` is public."""

    def __init__(self, state: str) -> None:
        super().__init__(state)
        self.state = state


class Busy(Exception):
    """The queue is full, or this asker's share of it is (IR-545). Nothing
    was created. ``reason`` is a public code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


#: Serialises queue admission across processes, inside the submitting
#: transaction. Any constant no other code uses.
_QUEUE_LOCK = 545_001


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
    with transaction.atomic():
        # The Conversation, then its runs: the order finishing a run takes.
        Conversation.objects.select_for_update().filter(pk=prepared.conversation.pk).first()
        return _queue(user, prepared.conversation.pk, request)


def retry(run_id, user):
    """``(run, created)``: a new run asking ``run_id``'s question again, or
    the retry it already has. ``None`` when the run is not the asker's (or is
    gone), or while another run in its Conversation is unfinished.

    Raises `NotRetryable` unless the run ended without its answer, and `Busy`
    as any new question would. The worker prepares the request again as the
    asker, so a Conversation or override Turn they lost fails the retry.
    """
    with transaction.atomic():
        original = _lock_owned(run_id, user)
        if original is None:
            return None
        existing = AskRun.objects.filter(retry_of=original).first()
        if existing is not None:
            return existing, False
        if original.state not in RETRYABLE_STATES:
            raise NotRetryable(original.state)
        run = _queue(user, original.conversation_id, original.request, retry_of=original)
    return (run, True) if run is not None else None


def _queue(user, conversation_id, request: dict, *, retry_of=None):
    """Create a run and its `run_queued` event, dispatched once committed;
    ``None`` while the Conversation has an unfinished run. The caller holds
    the Conversation's lock."""
    busy = AskRun.objects.select_for_update().filter(
        conversation_id=conversation_id, state__in=(QUEUED, RUNNING),
    )
    if any(not _expire_overdue(run) for run in busy):
        return None
    _admit_to_queue(user)
    deadline = timezone.now() + timedelta(seconds=settings.AI_DURABLE_ASK_DEADLINE_SECONDS)
    run = AskRun.objects.create(
        user=user, conversation_id=conversation_id, request=request, deadline_at=deadline,
        retry_of=retry_of,
    )
    _append(run, None, "run_queued", {
        "run_id": str(run.pk), "state": QUEUED, "deadline_at": deadline.isoformat(),
        "retry_of": str(retry_of.pk) if retry_of is not None else None,
    })
    transaction.on_commit(lambda: _dispatch(run.pk))
    return run


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


def _admit_to_queue(user) -> None:
    """Raise `Busy` unless the queue has room for one more of ``user``'s
    questions. Called inside `submit`'s transaction."""
    from apps.ai.admission.limits import NotConfigured, enforcing, read_limits

    if not enforcing():
        return
    try:
        limits = read_limits()
    except (NotConfigured, ImproperlyConfigured):
        raise Busy("not_configured") from None
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_QUEUE_LOCK])
    # A run past its deadline and grace holds no place: nothing will run it.
    cutoff = timezone.now() - timedelta(seconds=settings.AI_DURABLE_ASK_STALE_SECONDS)
    unfinished = AskRun.objects.filter(state__in=(QUEUED, RUNNING), deadline_at__gt=cutoff)
    if unfinished.filter(user=user).count() >= limits.queue_per_user:
        raise Busy("user_queue_full")
    if unfinished.count() >= limits.queue_depth:
        raise Busy("queue_full")


def _journal_capacity(run: AskRun, attempt, answer_state=None) -> None:
    """Journal the refusals this run met, when they cost it its answer: the
    run ends without one, or with one no model wrote. A refused rerank that
    only degraded retrieval under a generated answer is not "busy". Locked
    caller."""
    from apps.ai.answers.citations import GENERATED

    if answer_state == GENERATED:
        return
    scope = admission_scope.current_run()
    if scope is not None and scope.denials:
        _append(run, attempt, "capacity_limited", {
            "status": "busy", "reasons": sorted(set(scope.denials)),
        })


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

                _journal_capacity(run, self._attempt, answer.state)
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
    run = AskRun.objects.select_related("user").filter(pk=attempt.run_id).first()
    if run is None:
        raise StaleAttempt(str(attempt.pk))
    left = (run.deadline_at - timezone.now()).total_seconds()
    # Everything this delivery sends to a vendor -- the resolver included --
    # is charged to the run's own budget and bounded by the time left until
    # the deadline fixed at submission (IR-545). A redelivery opens the same
    # run key and the same deadline; neither is reset.
    with admission_scope.run(run_scope(run)), \
            model_call_deadline(max(0.0, left)):
        _answer_run(attempt, run)


def run_scope(run: AskRun) -> admission_scope.RunScope:
    """The admission scope a run's provider attempts are charged to, halted
    once the run is cancelled (IR-548)."""
    pk = run.pk
    return admission_scope.RunScope(
        f"ask:{pk}", halted=lambda: AskRun.objects.filter(pk=pk, state=CANCELLED).exists(),
    )


def _answer_run(attempt: AskRunAttempt, run: AskRun) -> None:
    from django.http import Http404

    from apps.ai.views.chatbot import prepare_ask

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
        with transaction.atomic():
            _journal_capacity(_locked(attempt), attempt)
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
    elif event.name in ("candidates_selected", "candidates_updated"):
        data = _visible_candidates(user, data)
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


def _visible_candidates(user, data: dict) -> dict:
    """A candidate event as it reads now: only Records the reader may see, and
    their current titles. One that is not visible is simply absent (IR-546)."""
    rows = data["candidates"]
    titles = dict(
        Record.objects.visible_to(user)
        .filter(pk__in={row["record_id"] for row in rows}).values_list("pk", "title")
    )
    return {**data, "candidates": [
        {**row, **({"title": titles[row["record_id"]]} if "title" in row else {})}
        for row in rows if row["record_id"] in titles
    ]}


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
