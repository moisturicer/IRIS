import csv
import json

from django.http import StreamingHttpResponse
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from core.permissions import IsAdmin
from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditFilters(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=AuditEvent.EVENT_TYPE_CHOICES, required=False)
    record = serializers.IntegerField(min_value=1, required=False)
    user = serializers.IntegerField(min_value=1, required=False)
    # `from` is a Python keyword; declare date fields through get_fields.
    def get_fields(self):
        fields = super().get_fields()
        fields.update({name: serializers.DateField(required=False) for name in ("from", "to")})
        return fields

    def validate(self, values):
        if values.get("from") and values.get("to") and values["from"] > values["to"]:
            raise serializers.ValidationError("From date must be on or before To date.")
        return values


class AuditEventListView(generics.ListAPIView):
    """
    GET /audit/
    RDCO only (ADR-009). Was DRF IsAdminUser, which reads Django's
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
        qs = AuditEvent.objects.select_related("user__role", "record").order_by("-created_at", "-id")

        filters = AuditFilters(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        params = filters.validated_data

        event_type = params.get("event_type")
        record_id  = params.get("record")
        user_id    = params.get("user")
        from_date  = params.get("from")
        to_date    = params.get("to")

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


CSV_COLUMNS = (
    "created_at", "event_type", "actor_id", "actor_role", "record_id", "party",
    "from_party", "to_party", "outcome", "version", "policy", "preserved_parties",
    "reset_parties", "request_id", "item_ids", "reason", "metadata_json",
)


class CsvBuffer:
    def write(self, value):
        return value


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    # Quoting alone does not stop spreadsheet formula evaluation.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


class AuditEventExportView(AuditEventListView):
    """The same RDCO-only history and filters, all rows in insertion order."""

    def get(self, request, *args, **kwargs):
        rows = self.get_queryset().order_by("id")

        def content():
            writer = csv.writer(CsvBuffer())
            yield writer.writerow(CSV_COLUMNS)
            for row in rows.iterator(chunk_size=1000):
                meta = row.metadata
                values = {
                    **{key: meta.get(key) for key in CSV_COLUMNS},
                    "created_at": row.created_at.isoformat(),
                    "event_type": row.event_type,
                    "actor_id": row.user_id,
                    "actor_role": row.user.role.name if row.user and row.user.role else "",
                    "record_id": row.record_id,
                    "request_id": meta.get("request"),
                    "item_ids": [item["id"] for item in meta.get("items", [])],
                    "metadata_json": meta,
                }
                yield writer.writerow([csv_cell(values[key]) for key in CSV_COLUMNS])

        response = StreamingHttpResponse(content(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="iris-audit.csv"'
        response["Cache-Control"] = "no-store"
        return response
