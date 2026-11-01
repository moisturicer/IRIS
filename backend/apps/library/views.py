"""
The reader's saved Records (IR-566, ADR-044 §3-§5).

Two rules hold for every request:

* **The owner is the authenticated user.** No body or URL names an owner, and
  every query starts from `SavedRecord.objects.filter(owner=request.user)`, so
  another reader's saves cannot be addressed at all.
* **The Record is rechecked against `Record.objects.visible_to(user)`** -- the
  one visibility predicate. Saving a Record you cannot read is a 404 identical
  to a missing one. A saved Record you can no longer read is listed as
  `{"record_id": <id>, "available": false}` and nothing else: the id is the
  one the reader supplied, so it discloses nothing new.

Every write is idempotent, so the interface can retry and roll back without
double counting.
"""

from django.db import transaction
from django.db.models import Count
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.records.models import Record
from apps.records.serializers import RecordListSerializer
from core.enums import ReadingStatus

from .models import SavedRecord

#: Absent from the body means "leave the status as it is".
_UNSET = object()


def _readable(user):
    return (
        Record.objects.visible_to(user)
        .select_related("classification", "record_type", "ai_overview")
        .prefetch_related("authors")
        .annotate(file_count=Count("files", distinct=True))
    )


def _entry(save, record, context):
    if record is None:
        return {"record_id": save.record_id, "available": False}
    return {
        "record_id": save.record_id,
        "available": True,
        "reading_status": save.reading_status,
        "saved_at": save.saved_at,
        "updated_at": save.updated_at,
        "record": RecordListSerializer(record, context=context).data,
    }


def _reading_status(data):
    if not isinstance(data, dict) or "reading_status" not in data:
        return _UNSET
    value = data["reading_status"]
    if value is None or value == "":
        return None
    if value not in ReadingStatus.values:
        raise ValidationError({"reading_status": [f"Must be one of {', '.join(ReadingStatus.values)}, or null."]})
    return value


class SavedRecordListView(APIView):
    """GET /library/saves/ -- the reader's saves, newest first."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        saves = list(SavedRecord.objects.filter(owner=request.user).order_by("-saved_at", "-pk"))
        records = {r.pk: r for r in _readable(request.user).filter(pk__in=[s.record_id for s in saves])}
        context = {"request": request}
        return Response({"results": [_entry(s, records.get(s.record_id), context) for s in saves]})


class SavedRecordDetailView(APIView):
    """
    PUT /library/saves/<record_id>/ saves the Record, optionally with a
    `reading_status` (one of `ReadingStatus`, or null to clear it).
    DELETE unsaves it; deleting what is not saved is still a 204.
    """

    permission_classes = [IsAuthenticated]

    def put(self, request, record_id):
        reading_status = _reading_status(request.data)
        record = _readable(request.user).filter(pk=record_id).first()
        if record is None:
            raise NotFound()

        with transaction.atomic():
            save, created = SavedRecord.objects.select_for_update().get_or_create(
                owner=request.user,
                record_id=record.pk,
                defaults={"reading_status": None if reading_status is _UNSET else reading_status},
            )
            if not created and reading_status is not _UNSET and save.reading_status != reading_status:
                save.reading_status = reading_status
                save.save(update_fields=["reading_status", "updated_at"])

        return Response(
            _entry(save, record, {"request": request}),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, record_id):
        # No visibility check: removing your own row discloses nothing, and a
        # reader must be able to drop a save that has become unavailable.
        SavedRecord.objects.filter(owner=request.user, record_id=record_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
