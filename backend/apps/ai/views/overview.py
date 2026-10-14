"""The paper view's AI Overview endpoint (IR-334)."""

from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.ai.overview import overview_for
from apps.records.models import Record


class AIOverviewThrottle(UserRateThrottle):
    """
    A cached read and its polling, not a paid question: it must not draw on
    `ai_query`, which bounds Ask IRIS. Opening sixty records used to lock a
    reader out of both (IR-569). Generation stays one claim per record.
    """

    scope = "ai_overview"


class RecordOverviewView(APIView):
    """
    GET /api/v1/ai/records/<id>/overview/

    The record's AI Overview, generated once and cached (IR-334). The paper
    view used to ask `/ai/ask/` on every mount, so opening a record was a paid
    vendor call every time.

    The record is looked up through `Record.objects.visible_to(user)`, so a
    reader without access gets a 404 identical to a missing record rather than
    a 403 that would confirm it exists.

    Disclosure is checked explicitly before reading a cached overview or
    queueing generation. A refusal returns no overview and calls no model.

    `generating` is a persisted claim, so concurrent readers share one queued
    task. `unavailable` means disclosure was refused or generation failed, and
    can be retried explicitly with `?retry=true`.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIOverviewThrottle]

    def get(self, request, pk: int):
        record = get_object_or_404(Record.objects.visible_to(request.user), pk=pk)
        retry = request.query_params.get("retry", "").lower() == "true"
        return Response(overview_for(record, retry=retry))
