"""The Conversation endpoints (IR-295, ADR-019).

Both views scope through `Conversation.objects.owned_by`, and that is the
whole authorization story - scoped queryset rather than permission class,
the IR-153 shape, so a refusal is a 404 identical to a missing row.

Staff are excluded, unlike everywhere else in IRIS: a transcript records what
someone asked about confidential IP (IR-294 Privacy).
"""
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.ai.models import Conversation
from apps.ai.serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
)


class ConversationListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/ai/conversations/   — the caller's own, most recent first
    POST /api/v1/ai/conversations/   — start one, optionally scoped to a Record
    """

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Conversation.objects.owned_by(self.request.user)

    def perform_create(self, serializer):
        # The owner comes from the request; `user` is not writable.
        serializer.save(user=self.request.user)


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
