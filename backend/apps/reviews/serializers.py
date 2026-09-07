from django.utils import timezone
from rest_framework import serializers

from .clearance_state import peer_summary
from .models import Review, RecordAuthPin


def queue_rows(records, *, viewer_office=None, request=None) -> list[dict]:
    """Review-queue rows, with the context a reviewer needs to triage (IR-139).

    `reviews/views.py::pending` already scopes each office to the records it may
    act on -- ITSO to `itso_review` with a pending ITSO clearance, and so on --
    but the payload never said so, so a KTTO reviewer and an IERC reviewer saw
    byte-identical rows. The filtering was right and invisible. These four
    additions are what make it legible:

    * `stage_label`   -- what the record is waiting for
    * `your_office`   -- which clearance *this viewer* would be recording, so
                         approving reads as "clear for IERC", not "approve"
    * `peers`         -- what the other offices have already decided (status
                         only, never their comments -- see `peer_summary`)
    * `waiting_since` -- how long it has sat, the only triage signal in a queue
                         where every row is otherwise equally urgent

    Sorted oldest-first: a queue that hides the longest wait on page two is a
    queue that produces the wait.
    """
    from apps.records.serializers import RecordListSerializer

    records = list(records)
    base = RecordListSerializer(records, many=True, context={"request": request}).data
    now = timezone.now()

    rows = []
    for record, row in zip(records, base):
        clearances = list(record.clearances.all())
        own = next((c for c in clearances if c.office == viewer_office), None)
        # The last decision on this record is when its current wait began; a
        # never-reviewed record has been waiting since it was submitted.
        latest = record.reviews.order_by("-created_at").first()
        since = latest.created_at if latest else record.created_at

        rows.append(
            {
                **row,
                "stage": record.pipeline_status,
                "stage_label": record.get_pipeline_status_display(),
                "your_office": viewer_office,
                "your_office_label": own.get_office_display() if own else None,
                "peers": peer_summary(clearances, excluding=viewer_office),
                "waiting_since": since.isoformat(),
                "waiting_days": max((now - since).days, 0),
                "resubmitted": (record.resubmission_count or 0) > 0,
                "resubmission_count": record.resubmission_count or 0,
            }
        )

    rows.sort(key=lambda r: r["waiting_since"])
    return rows


class ReviewSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True)

    class Meta:
        model  = Review
        fields = ["id", "record", "reviewed_by", "reviewed_by_name", "stage", "status", "comment", "created_at"]
        read_only_fields = ["reviewed_by", "stage", "created_at"]


class ReviewWriteSerializer(serializers.Serializer):
    record_id = serializers.IntegerField()
    status    = serializers.ChoiceField(choices=["approved", "declined", "rejected"])
    comment   = serializers.CharField(required=False, allow_blank=True)


class RecordAuthPinSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecordAuthPin
        fields = ["id", "record", "email", "is_used", "created_at"]
        read_only_fields = ["pin", "is_used"]
