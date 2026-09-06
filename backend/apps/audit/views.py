from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsAdmin
from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventListView(generics.ListAPIView):
    """
    GET /audit/
    RDCO only -- SRS FR-M6-06. Was DRF IsAdminUser, which reads Django's
    is_staff flag and therefore admitted all four offices (IR-165). Supports filtering via query params:
      ?event_type=LOGIN
      ?record=<id>
      ?user=<id>
      ?from=YYYY-MM-DD   (inclusive)
      ?to=YYYY-MM-DD     (inclusive)
    """
    serializer_class   = AuditEventSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = AuditEvent.objects.select_related("user", "record").order_by("-created_at")

        event_type = self.request.query_params.get("event_type")
        record_id  = self.request.query_params.get("record")
        user_id    = self.request.query_params.get("user")
        from_date  = self.request.query_params.get("from")
        to_date    = self.request.query_params.get("to")

        if event_type:
            qs = qs.filter(event_type=event_type)
        if record_id:
            qs = qs.filter(record_id=record_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)

        return qs
