from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsStaff
from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventListView(generics.ListAPIView):
    """
    GET /audit/
    Staff-only. Supports filtering by ?event_type=LOGIN&record=<id>&user=<id>
    TODO: add DateFilter (from/to date range)
    """
    serializer_class   = AuditEventSerializer
    permission_classes = [IsAuthenticated, IsStaff]

    def get_queryset(self):
        qs = AuditEvent.objects.select_related("user", "record").order_by("-created_at")
        event_type = self.request.query_params.get("event_type")
        record_id  = self.request.query_params.get("record")
        user_id    = self.request.query_params.get("user")
        if event_type:
            qs = qs.filter(event_type=event_type)
        if record_id:
            qs = qs.filter(record_id=record_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs


class ActiveSessionsView(generics.ListAPIView):
    """
    GET /audit/sessions/
    Returns users who have a LOGIN event with no subsequent LOGOUT today.
    TODO: implement properly -- current stub returns last 50 login events.
    """
    serializer_class   = AuditEventSerializer
    permission_classes = [IsAuthenticated, IsStaff]

    def get_queryset(self):
        return AuditEvent.objects.filter(event_type=AuditEvent.LOGIN).select_related("user").order_by("-created_at")[:50]
