"""Ask IRIS endpoints — grounded Q&A and ranked retrieval over the chunk corpus.

**The switch-over (IR-283).** These three endpoints used to rank whole records
by PostgreSQL full-text search over `Record.search_vector` and answer from
titles and abstracts. They now answer from **passages** — spans of a record's
own text — through the stack `apps.ai.composition` assembles.

The change a reader notices is that an answer can come from a methodology
section no abstract mentions. The change that matters more is invisible: the
old path filtered with `publicly_visible()`, a second and narrower visibility
rule than the `visible_to(user)` predicate the rest of IRIS applies. **On
these three endpoints** there is now one predicate, applied inside retrieval
before anything is scored.

Said precisely, because it is not yet true repo-wide: `RecordViewSet.similar`
still ranks through `apps/ai/services/retrieval.search_records`, which is the
`publicly_visible()` path. It is narrower rather than wider, so it withholds
rather than leaks — but it is the second rule, and it goes when IR-285 deletes
that module.

The views hold no wiring. They parse a request, ask the composition root for a
retriever or an answer service, and shape the reply — which is what makes the
whole path drivable from a test with deterministic fakes.
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.ai.answers.citations import NO_SOURCES, UNAVAILABLE
from apps.ai.composition import composition_root
from apps.ai.presentation import citations, passage, record_sources

MAX_QUESTION_LENGTH = 2000

#: How many passages ground an answer, and the ceiling on any `top_k`. The
#: ceiling is a cost control as much as a sanity one: every passage above it
#: is prompt the vendor is paid for and a reader does not read.
DEFAULT_TOP_K = 5
MAX_TOP_K = 20

#: What the wire calls each answer state. The API's own names, mapped from the
#: domain's rather than shared with them: `GroundedAnswer.state` is what the
#: service decided, and this is what a client has been told to expect.
GENERATIVE_MODE = "generative"
NO_RESULTS_MODE = "no_results"
UNAVAILABLE_MODE = "unavailable"
_WIRE_MODE = {
    NO_SOURCES: NO_RESULTS_MODE,
    UNAVAILABLE: UNAVAILABLE_MODE,
}

NO_RESULTS_MESSAGE = (
    "No readable sources in the CIT-U repository matched that question. Try "
    "different keywords, or browse Discover to see what is available."
)

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


class ChatQueryView(APIView):
    """
    POST /api/v1/ai/ask/
    Body: {"question": str, "top_k": int?}

    Returns an answer grounded in passages the asker is permitted to read,
    with the records those passages came from.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request):
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

        service = composition_root().answer_service(
            max_sources=_parse_top_k(request.data.get("top_k"))
        )
        answer = service.answer(question, request.user)
        mode = _WIRE_MODE.get(answer.state, GENERATIVE_MODE)

        # `answer` is a written answer or it is null. The two non-answers —
        # nothing found, and no model reachable — say so in `message`, so a
        # client rendering `answer` can never present an apology as a finding.
        #
        # `message` also carries the degradation note when an answer *was*
        # written from fallback results. Here rather than in the client: a
        # client composing its own sentence about how the backend retrieved
        # is a second wording of one fact, and the two drift.
        if mode == GENERATIVE_MODE:
            body = {"answer": answer.text, "message": None}
        elif mode == NO_RESULTS_MODE:
            body = {"answer": None, "message": NO_RESULTS_MESSAGE}
        else:
            body = {"answer": None, "message": answer.text}

        return Response(
            {
                **body,
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
            }
        )
