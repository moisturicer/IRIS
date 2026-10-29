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
from rest_framework.response import Response

from apps.ai.models import Conversation
from apps.records.models import Record
from apps.ai.serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
)


class ConversationListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/ai/conversations/?record=<id>   — the caller's own, most recent first
    POST /api/v1/ai/conversations/               — start one, optionally scoped to a Record
    """

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = Conversation.objects.owned_by(self.request.user)
        # ``?record=`` is how Paper Chat finds the Conversation it already
        # has for this paper, if any (IR-298) -- filtered on top of
        # `owned_by`, never instead of it, so this can only ever narrow the
        # caller's own list. A malformed id matches nothing rather than 500ing.
        record_param = self.request.query_params.get("record")
        if record_param is not None:
            try:
                queryset = queryset.filter(record_id=int(record_param))
            except (TypeError, ValueError):
                return queryset.none()
        if self.request.query_params.get("default") == "true" and record_param is not None:
            # Before the first atomic claim, continue legacy history. GET
            # never creates or elects a default merely by opening the panel.
            default = queryset.filter(is_default=True)
            return default if default.exists() else queryset[:1]
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reuse = serializer.validated_data.pop("reuse_default", False)
        if not reuse:
            self.perform_create(serializer)
            return Response(serializer.data, status=201)
        record = serializer.validated_data["record"]
        with transaction.atomic():
            # Stable lock even when no Conversation exists. All creation and
            # legacy adoption for this paper passes through this same row.
            Record.objects.select_for_update().get(pk=record.pk)
            owned = Conversation.objects.filter(user=request.user, record=record)
            conversation = owned.filter(is_default=True).first()
            if conversation is None:
                conversation = owned.first()
                if conversation is None:
                    conversation = Conversation.objects.create(user=request.user, record=record, is_default=True)
                else:
                    conversation.is_default = True
                    conversation.save(update_fields=["is_default"])
        return Response(ConversationDetailSerializer(conversation, context=self.get_serializer_context()).data)

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

    def perform_destroy(self, instance):
        # Lock the row before collecting what cascades, in the order a queued
        # run finishing takes it (IR-544, `apps.ai.durable`): a Turn that run
        # writes is then either collected here or never written.
        with transaction.atomic():
            Conversation.objects.select_for_update().filter(pk=instance.pk).first()
            instance.delete()
