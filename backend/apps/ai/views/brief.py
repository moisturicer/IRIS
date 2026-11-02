"""Authorized, on-demand paper briefs for comparisons (IR-556)."""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.briefs import brief_for
from .chatbot import AIQueryThrottle
from apps.ai.grants.reads import research_records


class PaperBriefView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AIQueryThrottle]

    def post(self, request, pk):
        record = get_object_or_404(research_records(request.user), pk=pk)
        return Response(brief_for(record, user=request.user, retry=request.data.get("retry") is True))
