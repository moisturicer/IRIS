"""Authorized, on-demand paper briefs for comparisons (IR-556)."""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.briefs import brief_for
from apps.records.models import Record
from .chatbot import AIQueryThrottle


class PaperBriefView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request, pk):
        record = get_object_or_404(Record.objects.visible_to(request.user), pk=pk)
        return Response(brief_for(record, user=request.user, retry=request.data.get("retry") is True))
