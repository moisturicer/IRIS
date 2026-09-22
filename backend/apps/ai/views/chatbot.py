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
from django.http import Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.ai import resolution
from apps.ai.composition import composition_root
from apps.ai.conversations import record_turn
from apps.ai.models import Conversation
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


def _conversation_for(request):
    """The Conversation this question belongs to, or ``None`` for a one-off.

    Looked up inside the caller's own conversations, so somebody else's id is
    a 404 identical to an id that never existed — a refusal that confirmed a
    transcript exists would leak the one thing this model is private for. A
    malformed id takes the same exit rather than a 500.
    """
    raw = request.data.get("conversation_id")
    if raw in (None, ""):
        return None
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        raise Http404
    try:
        return Conversation.objects.select_related("record").get(
            pk=pk, user=request.user
        )
    except Conversation.DoesNotExist:
        raise Http404


def _recent_turns(conversation: Conversation) -> list:
    """The Conversation's most recent Turns, oldest first, bounded at the
    source. Serves both resolution (IR-296) and the answering prompt
    (IR-297); older Turns are memory's job, not this function's.
    """
    return list(
        conversation.turns.order_by("-id")[: resolution.MAX_HISTORY_TURNS]
    )[::-1]


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
    outright — no model call — on the first Turn and on a question with no
    back-reference, and a failed resolution falls back to the raw question
    rather than erroring.

    **A Conversation scoped to a Record retrieves only that Record's
    passages by default** (IR-298, ADR-026 §9). ``widen`` opts one question
    out of that scope to search every paper instead — never automatic, and
    never remembered onto the next question. It does nothing when the
    Conversation carries no Record, or when there is no Conversation at all.
    Whether this answer was actually widened travels back on the response as
    ``widened`` and is stored on the Turn, so a reopened transcript can say
    which scope produced each answer rather than guessing from its citations.

    **Recent Turns go into the answering prompt verbatim; older ones are
    found by memory recall, never summarised** (IR-297). The search vector
    is stored on the new Turn as its own memory vector, at no extra cost.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request):
        conversation = _conversation_for(request)
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response(
                {"detail": "question is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(question) > MAX_QUESTION_LENGTH:
            return Response(
                {"detail": f"question must be at most {MAX_QUESTION_LENGTH} characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        history = _recent_turns(conversation) if conversation is not None else []

        resolved_question = None
        if conversation is not None:
            resolver = composition_root().resolver()
            if resolver is not None:
                resolved_question = resolver.resolve(question, history)
        effective_question = resolved_question or question

        # Widened only when there was a scope to widen *from* -- an unscoped
        # Conversation, or no Conversation, was never narrower than "every
        # paper", so `widen` has nothing to do there.
        widen = bool(request.data.get("widen"))
        scoped_to = conversation.record if conversation is not None else None
        widened = scoped_to is not None and widen
        scope_record = None if widened else scoped_to

        service = composition_root().answer_service(
            max_sources=_parse_top_k(request.data.get("top_k")),
            record=scope_record,
        )
        answer = service.answer(
            effective_question, request.user, conversation=conversation, history=history
        )
        mode = answer_mode(answer.state)

        if conversation is not None:
            record_turn(conversation, question, answer, resolved_question, widened)

        return Response(
            {
                **answer_body(mode, answer.text),
                "conversation_id": None if conversation is None else conversation.pk,
                # What retrieval actually searched with, shown so a reader
                # can see when IRIS guessed wrong (IR-296). Null whenever
                # resolution did not run or changed nothing.
                "resolved_question": resolved_question,
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
                "widened": widened,
            }
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
