"""What is left of Django's Ask IRIS endpoints after IR-957.

Every reader question is answered by the AI runtime (ADR-049 §27). The routes
that used to answer -- `/ask/`, `/ask/stream/`, a queued run's retry and
`/search/` -- answer 410 Gone through `RetiredAnswerView`, so no second path
reads corpus text. What stays reads only what a reader already owns: the
journal of a queued question asked before the switch, its cancel, and the
deployment status.
"""
from django.http import Http404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.ai import public as public_protocol
from apps.ai.composition import composition_root
from apps.ai.streaming import EventStreamResponse
from apps.ai.grants.reads import research_records


class AIQueryBurstThrottle(UserRateThrottle):
    """Ask IRIS's per-minute burst (IR-999); `AIQueryThrottle` is its daily backstop."""

    scope = "ai_query_burst"


class AIQueryThrottle(UserRateThrottle):
    """Retrieval hits the DB and may hit a paid provider — cap it per user."""


class RetiredAnswerView(APIView):
    """Django no longer answers questions or searches passages (IR-957)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryBurstThrottle, AIQueryThrottle]

    def _gone(self, request, *args, **kwargs):
        return Response(
            {"status": "retired",
             "detail": "Ask IRIS now answers through the AI runtime. Reload the page to continue."},
            status=status.HTTP_410_GONE,
        )

    post = _gone


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
        return EventStreamResponse(
            durable.follow(pk, request.user, after=after, public=public_protocol.requested(request))
        )


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
        from apps.ai.models.queued import CANCELLED

        run = durable.cancel(pk, request.user)
        if run is None:
            raise Http404
        body = {"run_id": str(run.pk), "state": run.state}
        return Response(body, status=200 if run.state == CANCELLED else status.HTTP_409_CONFLICT)


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

        try:
            space = get_active_embedding_space()
        except ImproperlyConfigured:
            # Not an error to report on: a deployment that has not indexed
            # yet has no active space, and saying so is this endpoint's job.
            space = None

        indexed_records = 0
        if space is not None:
            visible = research_records(request.user).values("pk")
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
