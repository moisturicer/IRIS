"""The Conversation endpoints (IR-295, ADR-019).

Both views scope through `Conversation.objects.owned_by`, and that is the
whole authorization story - scoped queryset rather than permission class,
the IR-153 shape, so a refusal is a 404 identical to a missing row.

Staff are excluded, unlike everywhere else in IRIS: a transcript records what
someone asked about confidential IP (IR-294 Privacy).
"""
from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.ai.models import Conversation
from apps.ai.serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
)


class ConversationListView(generics.ListAPIView):
    """
    GET  /api/v1/ai/conversations/?record=<id>   — the caller's own, most recent first

    Read-only since IR-957: the AI runtime keeps its own Conversations, so a
    Django Conversation is history a reader can open, rename or delete, never
    a new place to ask.
    """

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = Conversation.objects.owned_by(self.request.user)
        # ``?record=`` narrows the caller's own list to one paper's (IR-298);
        # a malformed id matches nothing rather than 500ing.
        record_param = self.request.query_params.get("record")
        if record_param is not None:
            try:
                queryset = queryset.filter(record_id=int(record_param))
            except (TypeError, ValueError):
                return queryset.none()
        return queryset


class ConversationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/ai/conversations/<pk>/   — the conversation and its Turns
    PATCH  /api/v1/ai/conversations/<pk>/   — rename it
    DELETE /api/v1/ai/conversations/<pk>/   — and its Turns with it
    """

    serializer_class = ConversationDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.owned_by(self.request.user)

    def perform_destroy(self, instance):
        # Lock the row before collecting what cascades, in the order a queued
        # run finishing takes it (IR-544, `apps.ai.durable`): a Turn that run
        # writes is then either collected here or never written.
        with transaction.atomic():
            Conversation.objects.select_for_update().filter(pk=instance.pk).first()
            instance.delete()
