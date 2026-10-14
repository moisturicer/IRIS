"""Ask IRIS endpoints — grounded Q&A and ranked retrieval over the chunk corpus.

**The switch-over (IR-283).** These three endpoints used to rank whole records
by PostgreSQL full-text search over `Record.search_vector` and answer from
titles and abstracts. They now answer from **passages** — spans of a record's
own text — through the stack `apps.ai.composition` assembles.

The change a reader notices is that an answer can come from a methodology
section no abstract mentions. The change that matters more is invisible: the
old path filtered with `publicly_visible()`, a second and narrower visibility
rule than the `visible_to(user)` predicate the rest of IRIS applies. There is
now one predicate, applied inside retrieval before anything is scored — and
since IR-285 deleted the record-level stack and moved `RecordViewSet.similar`
onto record vectors, that is true of every retrieval path rather than only of
these three endpoints. `apps/ai/tests/test_one_retrieval_stack.py` fails if
the second rule comes back.

The views hold no wiring. They parse a request, ask the composition root for a
retriever or an answer service, and shape the reply — which is what makes the
whole path drivable from a test with deterministic fakes.
"""
import json
from contextlib import closing

from django.http import Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.ai.history import recent_window
from apps.ai.answers.events import (
    AgentStep,
    CandidatesSelected,
    CandidatesUpdated,
    CitationsResolved,
    Done,
    ReasoningDelta,
    RetrievalFinished,
    TextDelta,
)
from apps.ai.composition import composition_root
from apps.ai.models import Conversation
from apps.ai.orchestrator import ChatOrchestrator, ChatQuestion
from apps.ai.streaming import EventStreamResponse
from apps.ai.presentation import (
    answer_body,
    answer_mode,
    citations,
    passage,
    record_sources,
)

#: A plain abuse guard, and since IR-295 nothing more than that. It used to be
#: load-bearing by accident: the frontend glued the whole transcript into the
#: question, so a conversation died at roughly six turns when the transcript
#: crossed this line. History now travels as a conversation id, so a question
#: is a question again and 2,000 characters is a generous bound on one.
MAX_QUESTION_LENGTH = 2000

#: How many passages ground an answer, and the ceiling on any `top_k`. The
#: ceiling is a cost control as much as a sanity one: every passage above it
#: is prompt the vendor is paid for and a reader does not read.
DEFAULT_TOP_K = 5
MAX_TOP_K = 20

#: The answer states and the `answer`/`message` pair each one puts on the wire
#: live in `apps/ai/presentation.py` (IR-295). They moved because a stored Turn
#: is replayed into the same shape, and two copies of that mapping is how a
#: reopened transcript starts presenting "no model was reachable" as an answer.

#: No degradation *sentence* here, deliberately, and this is a reversal of a
#: decision IR-283 made the other way. That version put the wording on the
#: server so a client could not compose a second copy of it. Two surfaces then
#: needed it phrased differently — "weigh this answer" in the chat, "weigh this
#: summary" on a paper — which one server string cannot do without knowing
#: which screen asked. So the contract is the *fact*, `degraded`, and the
#: sentence belongs to whoever renders it, in one place per client
#: (`components/PassageQuote.DegradedNotice`).


class AIQueryThrottle(UserRateThrottle):
    """Retrieval hits the DB and may hit a paid provider — cap it per user."""

    scope = "ai_query"


def _parse_top_k(raw, default: int = DEFAULT_TOP_K) -> int:
    try:
        return max(1, min(int(raw), MAX_TOP_K))
    except (TypeError, ValueError):
        return default


def _conversation_for(data, user):
    """The Conversation this question belongs to, or ``None`` for a one-off.

    Looked up inside the caller's own conversations, so somebody else's id is
    a 404 identical to an id that never existed — a refusal that confirmed a
    transcript exists would leak the one thing this model is private for. A
    malformed id takes the same exit rather than a 500.
    """
    raw = data.get("conversation_id")
    if raw in (None, ""):
        return None
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        raise Http404
    try:
        return Conversation.objects.select_related("record").get(
            pk=pk, user=user
        )
    except Conversation.DoesNotExist:
        raise Http404


def _recent_turns(conversation: Conversation) -> list:
    """The Conversation's most recent Turns, oldest first, bounded by a
    token budget. Serves both resolution (IR-296) and the answering prompt
    (IR-297); older Turns are memory's job, not this function's.

    **This is the only place the verbatim window is decided** (IR-449). The
    list returned here goes to `QuestionResolver.resolve` and on to
    `answers.citations.build_prompt` unchanged, and neither narrows it
    further, so the two prompts cannot disagree about how much history there
    was. It used to be a fixed six Turns, which spent a fraction of the room
    available on short exchanges and several times the room intended on long
    ones; `apps.ai.history` explains why the budget is counted locally and
    what the margin on it is for.

    The query is bounded separately, at `HISTORY_CANDIDATE_LIMIT` rows
    (`apps.ai.history`), so
    filling a 3000-token budget never reads a five-hundred-Turn
    Conversation. That is a bound on the fetch and not the window -- the
    budget is what decides how many of those rows are used.

    **Failed and refused Turns are not here** (IR-448, ADR-026 §13):
    `in_model_history()` keeps `no_sources`, `unavailable` and `partial` out,
    so neither prompt is shown a refusal as a prior answer. The reader still
    sees them -- `conversations.turns_for_reader` is deliberately unfiltered.
    Both bounds apply *after* the exclusion, so a run of failures does not eat
    the window and leave the model with less real history than it has.
    """
    return recent_window(conversation.turns.all())


def prepare_ask(data, user, *, resolve: bool = True):
    """Parse and validate one question, resolve it and its scope.

    Returns ``(prepared, None)`` on success or ``(None, error_response)`` on
    a validation failure the caller should return exactly as given -- a 400
    happens identically whether the answer that follows is one JSON body or
    a stream of events.

    ``resolve=False`` validates without the resolver's model call. A queued
    question (IR-544) is validated that way at submission and prepared again,
    resolution included, by the worker -- which re-checks the Conversation
    and any override Turn against the asker at the same time.
    """
    from apps.ai.routing.router import LANES

    route_override = data.get("route_override")
    if route_override is not None and (not isinstance(route_override, str) or route_override not in LANES):
        return None, Response({"detail": "route_override must name a supported lane."}, status=400)
    conversation = _conversation_for(data, user)
    question = (data.get("question") or "").strip()
    if not question:
        return None, Response(
            {"detail": "question is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    if len(question) > MAX_QUESTION_LENGTH:
        return None, Response(
            {"detail": f"question must be at most {MAX_QUESTION_LENGTH} characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    override_turn = None
    turn_reference = data.get("route_override_turn_id")
    if turn_reference is not None:
        if route_override is None or conversation is None:
            return None, Response({"detail": "An override Turn requires a lane and conversation."}, status=400)
        if type(turn_reference) is not int or turn_reference < 1:
            return None, Response({"detail": "route_override_turn_id must be a positive integer."}, status=400)
        override_turn = conversation.turns.filter(pk=turn_reference).first()
        if override_turn is None:
            raise Http404
        question = override_turn.question
        history = recent_window(conversation.turns.filter(pk__lt=override_turn.pk))
        resolved_question = override_turn.resolved_question or None
    else:
        # Only resolution and the answer read history; a queued submission
        # does neither in the request.
        history = _recent_turns(conversation) if conversation is not None and resolve else []
        resolved_question = None
        if conversation is not None and resolve:
            resolver = composition_root().resolver()
            if resolver is not None:
                resolved_question = resolver.resolve(question, history)
    effective_question = resolved_question or question

    # A saved override reuses the scope choice that produced the original Turn.
    widen = override_turn.widened if override_turn else bool(data.get("widen"))
    scoped_to = conversation.record if conversation is not None else None
    widened = scoped_to is not None and widen
    scope_record = None if widened else scoped_to

    return (
        ChatQuestion(
            conversation=conversation,
            question=question,
            effective_question=effective_question,
            resolved_question=resolved_question,
            history=history,
            widened=widened,
            scope_record=scope_record,
            route_override=route_override,
            override_turn_id=override_turn.pk if override_turn else None,
        ),
        None,
    )


class ChatQueryView(APIView):
    """
    POST /api/v1/ai/ask/
    Body: {"question": str, "top_k": int?, "conversation_id": int?, "widen": bool?}

    Returns an answer grounded in passages the asker is permitted to read,
    with the records those passages came from.

    ``conversation_id`` is optional and appends the question and its answer
    to that Conversation as a Turn (IR-295). Omitting it answers exactly as
    before and stores nothing: a one-off question needs no Conversation.

    **When the Conversation has history, the question is resolved into a
    standalone one before retrieval runs** (IR-296, ADR-026) — "what about
    its limitations?" becomes a question that names the paper. Retrieval and
    synthesis both see the resolved question; the raw one is what gets
    stored as ``question`` and shown back unchanged. Resolution is skipped
    outright — no model call — on the first Turn only; the word check that
    also skipped a question with no pronoun in it was deleted by IR-445,
    which is why this paragraph no longer claims one. A failed resolution
    falls back to the raw question rather than erroring.

    **A Conversation scoped to a Record retrieves only that Record's
    passages by default** (IR-298, ADR-026 §9). ``widen`` opts one question
    out of that scope to search every paper instead — never automatic, and
    never remembered onto the next question. It does nothing when the
    Conversation carries no Record, or when there is no Conversation at all.
    Whether this answer was actually widened travels back on the response as
    ``widened`` and is stored on the Turn, so a reopened transcript can say
    which scope produced each answer rather than guessing from its citations.

    **Recent Turns go into the answering prompt verbatim; older ones are
    found by memory recall, never summarised** (IR-297). How many count as
    recent is a token budget rather than a Turn count (IR-449,
    ``AI_HISTORY_TOKEN_BUDGET``), so a run of one-line exchanges carries
    further back than a run of long answers does. The search vector is
    stored on the new Turn as its own memory vector, at no extra cost.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request):
        prepared, error = prepare_ask(request.data, request.user)
        if error is not None:
            return error

        orchestrator = ChatOrchestrator(
            prepared, max_sources=_parse_top_k(request.data.get("top_k"))
        )
        answer = orchestrator.answer(request.user)
        return Response(done_body(prepared, orchestrator, answer))


def done_body(prepared, orchestrator, answer) -> dict:
    """The final answer's wire body, one shape for `/ask/` and `done`."""
    mode = answer_mode(answer.state)
    return {
        **answer_body(mode, answer.text, preserve_no_results=bool(orchestrator.metadata)),
        **orchestrator.metadata,
        "conversation_id": (
            None if prepared.conversation is None else prepared.conversation.pk
        ),
        # What retrieval actually searched with, shown so a reader
        # can see when IRIS guessed wrong (IR-296). Null whenever
        # resolution did not run or changed nothing.
        "resolved_question": prepared.resolved_question,
        # A citation is an object: the record it belongs to, the page,
        # and the quoted passage (IR-284). A bare record id asked a
        # reader to find the sentence themselves.
        "citations": citations(answer.citations),
        # Every passage the model was shown, not only the cited ones:
        # a reader who wants to check what IRIS read needs the list it
        # read, and a vendor failure returns it with no answer at all.
        "sources": record_sources(answer.sources),
        "mode": mode,
        "degraded": answer.degraded,
        # Whether this answer left its Conversation's Record scope
        # (IR-298) -- always false with no scope to have left.
        "widened": prepared.widened,
        # Whether the model produced any reasoning (IR-327), and the
        # reasoning itself (IR-381). Always false and always `None` from
        # `/ask/`: `answer()` calls `generate()`, not `stream()`, so that
        # endpoint never requests a reasoning channel at all. Sent anyway,
        # because the two endpoints' bodies are the same shape by contract
        # -- a client must end up in an identical state whichever one it
        # called.
        "had_reasoning": answer.had_reasoning,
        "reasoning": answer.reasoning or None,
    }


def event_payload(event) -> dict:
    """The wire body of one stream event other than `done`."""
    from apps.ai.routing.chat import RoutingDecided

    if isinstance(event, RoutingDecided):
        return {"routing": event.routing}
    if isinstance(event, (AgentStep, CandidatesSelected, CandidatesUpdated)):
        return event.wire()
    if isinstance(event, RetrievalFinished):
        return {
            "passage_count": event.passage_count,
            "record_count": event.record_count,
            "degraded": event.degraded,
        }
    if isinstance(event, (TextDelta, ReasoningDelta)):
        return {"text": event.text}
    if isinstance(event, CitationsResolved):
        return {"citations": citations(event.citations)}
    # RetrievalStarted, GenerationStarted -- no payload beyond the name.
    return {}


def _sse(event_name: str, data: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


class ChatStreamView(APIView):
    """
    POST /api/v1/ai/ask/stream/

    The same question `ChatQueryView` answers, as Server-Sent Events instead
    of one JSON body -- a reader-facing progress line as retrieval and
    generation happen, rather than a silent wait (IR-326). `/ask/` above is
    untouched and unrelated to this view beyond sharing its request parsing;
    a caller picks one endpoint, not both.

    Event vocabulary, in order: `retrieval_started`, `retrieval_finished`
    (a passage/record count for the progress line), `generation_started`,
    `reasoning_delta` and `text_delta` interleaved as the model produces
    them (IR-327 -- a reasoning delta never contains answer text and a text
    delta never contains reasoning, whichever channel the vendor actually
    sent it on), `citations_resolved`, `done` (the same
    `answer`/`citations`/`sources`/`mode`/`degraded`/`widened`/`had_reasoning`
    shape `ChatQueryView` returns, so a client ends up in an identical state
    either way -- plus `reasoning`, the same text the `reasoning_delta`
    events already carried, sent once at the end so a client that joined
    late, or reopens this Turn later, reads it from one place; IR-327's
    separation holds throughout, reasoning is never part of `answer` and is
    never scanned for citation markers). A
    memory recall (IR-297) gets no event of its own -- folded silently into
    retrieval, matching the synchronous path's own ordering.
    `generation_started` and every event after it are skipped outright when
    there are no readable sources to answer from.

    **A stream that never reaches `done` still persists (IR-328)** -- as a
    Turn with `state` `partial`, via `persist_partial` below. Unless it cut
    off before any answer text arrived (IR-377), in which case nothing is
    stored: a Turn whose answer is blank reads as a reply that is not there.

    **This stays a plain synchronous view.** Retrieval, the disclosure gate,
    memory recall and persistence are the exact same synchronous calls
    `ChatQueryView` makes; `EventStreamResponse` streams it under ASGI.
    The research lane adds `agent_step` events and `done.research` (IR-504).
    A listing adds `candidates_selected` (every candidate, relevance pending,
    as soon as chosen) and `candidates_updated` (new states by record id),
    then `done.listing` with every candidate in one state (IR-546).

    **With `AI_DURABLE_ASK` on, a question inside a Conversation is queued
    instead (IR-544).** The same response then follows the run's journal:
    `run_queued`, `run_started`, the events above, and `done` (or
    `run_failed`), each with an SSE `id:` a reader can reconnect from through
    `RunStreamView`. Leaving unsubscribes; the worker answers regardless.
    `apps/ai/durable.py` has the lifecycle.

    **Generation streams against the real configured model as of IR-334.**
    The IR-321 resilience decorators implement `stream()` now, rather than
    inheriting the port's buffering default, so a reader sees text as the
    model writes it instead of in one burst at the end. Retry and failover
    happen only before the first delta -- see `apps/ai/resilience/llm.py`.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request):
        from apps.ai import durable

        queued = durable.requested(request.data)
        prepared, error = prepare_ask(request.data, request.user, resolve=not queued)
        if error is not None:
            return error
        if queued:
            # Answered by a worker; this response only follows its journal,
            # so a disconnect unsubscribes and nothing else (IR-544).
            try:
                run = durable.submit(
                    prepared, request.user, request.data,
                    max_sources=_parse_top_k(request.data.get("top_k")),
                )
            except durable.Busy as busy:
                # Refused before anything was queued (IR-545): an explicit
                # busy status, not a run that would wait past its deadline.
                return Response(
                    {"detail": "IRIS is busy answering other questions. Please try again shortly.",
                     "status": "busy", "reason": busy.reason},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    headers={"Retry-After": "5"},
                )
            if run is None:
                return Response(
                    {"detail": "IRIS is still answering your previous question in this conversation."},
                    status=status.HTTP_409_CONFLICT,
                )
            return EventStreamResponse(durable.follow(run.pk, request.user))

        orchestrator = ChatOrchestrator(
            prepared, max_sources=_parse_top_k(request.data.get("top_k"))
        )

        def event_source():
            # The orchestrator records the Turn before `Done` reaches here,
            # and as `partial` on interruption (IR-328).
            # Closed explicitly, so a run never waits on garbage collection.
            events = orchestrator.answer_stream(request.user)
            with closing(events):
                for event in events:
                    if isinstance(event, Done):
                        body = done_body(prepared, orchestrator, event.answer)
                    else:
                        body = event_payload(event)
                    yield _sse(event.name, body)

        return EventStreamResponse(event_source())


class RunStreamView(APIView):
    """
    GET /api/v1/ai/ask/runs/<uuid>/stream/?after=N

    Reconnect to a queued question (IR-544): the run's public events after
    sequence ``N`` (or the SSE ``Last-Event-ID`` header), then the live tail
    until its terminal event. The same events, names and `id:` cursor that
    `/ask/stream/` sent before the connection dropped.

    Someone else's run is a 404 identical to one that never existed.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from apps.ai import durable
        from apps.ai.models import AskRun

        if not AskRun.objects.owned_by(request.user).filter(pk=pk).exists():
            raise Http404
        after = request.query_params.get("after", request.headers.get("Last-Event-ID", 0))
        try:
            after = max(0, int(after))
        except (TypeError, ValueError):
            after = 0
        return EventStreamResponse(durable.follow(pk, request.user, after=after))


class RunCancelView(APIView):
    """
    POST /api/v1/ai/ask/runs/<uuid>/cancel/

    Stop the asker's queued question (IR-548). 200 with ``cancelled`` once it
    is, or if it already was; 409 with the state it ended in when it had
    already finished. Someone else's run is a 404 identical to a missing one.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from apps.ai import durable

        run = durable.cancel(pk, request.user)
        if run is None:
            raise Http404
        body = {"run_id": str(run.pk), "state": run.state}
        return Response(body, status=200 if run.state == "cancelled" else status.HTTP_409_CONFLICT)


class RunRetryView(APIView):
    """
    POST /api/v1/ai/ask/runs/<uuid>/retry/

    Ask a run's question again as a new, linked run (IR-548): 201 with its
    id, which `RunStreamView` follows from the start. Repeating the request
    returns that same run with 200 instead of starting another. 409 while the
    run has not ended, once it ended with its answer, or while another run in
    its Conversation is unfinished; 503 when the queue is full.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request, pk):
        from apps.ai import durable
        from apps.ai.models import AskRun

        if not durable.enabled():
            if not AskRun.objects.owned_by(request.user).filter(pk=pk).exists():
                raise Http404
            return Response(
                {"detail": "Queued questions are switched off; ask the question again."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            result = durable.retry(pk, request.user)
        except durable.NotRetryable as refused:
            return Response(
                {"detail": "Only a question that ended without its answer can be retried.",
                 "run_id": str(pk), "state": refused.state},
                status=status.HTTP_409_CONFLICT,
            )
        except durable.Busy as busy:
            return Response(
                {"detail": "IRIS is busy answering other questions. Please try again shortly.",
                 "status": "busy", "reason": busy.reason},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": "5"},
            )
        if result is None:
            if not AskRun.objects.owned_by(request.user).filter(pk=pk).exists():
                raise Http404
            return Response(
                {"detail": "IRIS is still answering another question in this conversation."},
                status=status.HTTP_409_CONFLICT,
            )
        run, created = result
        return Response(
            {"run_id": str(run.pk), "retry_of": str(run.retry_of_id), "state": run.state},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SemanticSearchView(APIView):
    """
    POST /api/v1/ai/search/
    Body: {"query": str, "top_k": int?}

    Ranked retrieval without synthesis — the list behind an answer, from the
    same retriever, so what a reader browses is what an answer would cite.

    **`results` and `count` are passages** (IR-284), where they used to be
    records: several can come from one paper, and which passage matched is
    the thing a reader is browsing for. `sources` carries the record cards
    for those same passages, so nothing that had a card before loses one.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request):
        query = (request.data.get("query") or "").strip()
        if not query:
            return Response(
                {"detail": "query is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        limit = _parse_top_k(request.data.get("top_k"), 10)
        result = composition_root().retriever().retrieve(query, request.user, limit=limit)
        passages = [passage(p) for p in result.passages]
        return Response(
            {
                "results": passages,
                "count": len(passages),
                # The cards for the records those passages came from, so a
                # browsing reader sees whose work each quote is without a
                # fetch per result.
                "sources": record_sources(result.passages),
                "degraded": result.degraded,
            }
        )


class AIStatusView(APIView):
    """
    GET /api/v1/ai/status/

    What will actually happen if you ask something: which index answers are
    ranked against, and whether a model will write one. It used to report a
    hardcoded `"postgres_fts"`, which stayed true by accident and would have
    stayed printed after it stopped being true.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.core.exceptions import ImproperlyConfigured

        from apps.ai.models import get_active_embedding_space
        from apps.ai.models.chunk import ChunkEmbedding
        from apps.ai.policy.bypass import bypass_enabled
        from apps.records.models import Record

        try:
            space = get_active_embedding_space()
        except ImproperlyConfigured:
            # Not an error to report on: a deployment that has not indexed
            # yet has no active space, and saying so is this endpoint's job.
            space = None

        indexed_records = 0
        if space is not None:
            visible = Record.objects.visible_to(request.user).values("pk")
            indexed_records = (
                ChunkEmbedding.objects.filter(
                    space=space,
                    chunk__record__in=visible,
                    chunk__chunk_set__is_active=True,
                    chunk__deleted_at__isnull=True,
                )
                .values("chunk__record_id")
                .distinct()
                .count()
            )

        return Response(
            {
                "embedding_space": (
                    None
                    if space is None
                    else {
                        "id": space.pk,
                        "model_id": space.model_id,
                        "dimensions": space.dimensions,
                        "metric": space.metric,
                    }
                ),
                "generative": composition_root().generation_configured(),
                # Counted through `visible_to`, like everything else on this
                # path: a raw corpus total would tell an asker how many
                # records exist that they cannot see.
                "indexed_records": indexed_records,
                # Reported so the interface can say the gate is off and a demo
                # screenshot labels itself (IR-317, ADR-015 §A development
                # bypass condition 2). Removed with the bypass, by IR-250.
                "disclosure_bypass": bypass_enabled(),
            }
        )
