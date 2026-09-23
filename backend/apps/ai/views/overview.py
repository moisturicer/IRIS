"""The paper view's AI Overview endpoint (IR-334)."""

from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.overview import overview_for
from apps.records.models import Record

from .chatbot import AIQueryThrottle


class RecordOverviewView(APIView):
    """
    GET /api/v1/ai/records/<id>/overview/

    The record's AI Overview, generated once and cached (IR-334). The paper
    view used to ask `/ai/ask/` on every mount, so opening a record was a paid
    vendor call every time.

    The record is looked up through `Record.objects.visible_to(user)`, so a
    reader without access gets a 404 identical to a missing record rather than
    a 403 that would confirm it exists.

    Three states, and the client renders each differently: `ready` carries an
    overview, `not_indexed` means nothing has been extracted from this record
    yet, and `unavailable` means no model could be reached — which is not
    cached, so the next view tries again.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def get(self, request, pk: int):
        record = get_object_or_404(Record.objects.visible_to(request.user), pk=pk)
        return Response(overview_for(record, request.user))
