from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from .models import Record
from apps.reviews.models import ResubmissionRequest
from core.enums import (
    DELETE_REVIEW_STATUSES,
    PUBLICLY_VISIBLE_STATUSES,
    PipelineStatus,
    ResubmissionRequestState,
)

#: The statuses that mean "somebody is still reviewing this". One since
#: ADR-032: whoever holds a record, it is stored `in_review` (IR-260). The five
#: fixed-pipeline stages it replaced were deleted by IR-274.
IN_REVIEW_STATUSES = (PipelineStatus.IN_REVIEW,)


class DashboardStatsView(APIView):
    """
    GET /dashboard/stats/
    Returns counts used by the frontend dashboard cards.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        my_ids = Record.objects.filter(owners__user=user).values_list("pk", flat=True)
        return Response({
            "total_mine":       my_ids.count(),
            "pending_mine":     Record.objects.filter(pk__in=my_ids, pipeline_status__in=IN_REVIEW_STATUSES).count(),
            # The owner's own *accepted* work, not the public catalogue: since
            # IR-264 narrowed the public set to published only, reading it here
            # would drop a student's approved Proposal from their own count.
            # DELETE_REVIEW_STATUSES is exactly "accepted" (published, or an
            # approved/completed Proposal).
            "approved_mine":    Record.objects.filter(pk__in=my_ids, pipeline_status__in=DELETE_REVIEW_STATUSES).count(),
            # The owner's records a reviewer has asked to revise: an open
            # revision request, which replaced the stored `declined` (IR-274).
            "declined_mine":    ResubmissionRequest.objects.filter(
                record_id__in=my_ids, state=ResubmissionRequestState.OPEN,
            ).values("record_id").distinct().count(),
            # Staff-only totals -- return 0 for students
            "total_published":  Record.objects.filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES).count() if request.user.role else 0,
        })


class ClassificationChartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = (
            Record.objects.filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
            .values("classification__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return Response(list(data))


class PSCEDChartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = (
            Record.objects.filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES)
            .values("psced__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return Response(list(data))


# TODO (M07 — FR-M7-01 PipelineProgressView):
#   GET /dashboard/pipeline/<record_pk>/
#   Returns the per-office clearance breakdown for a single record.
#
#   Permission: [IsAuthenticated]; 403 if request.user is not an owner of the record AND not staff.
#
#   Response:
#     {
#       "pipeline_status": str,        # e.g. "in_review"
#       "clearances": [
#         { "office": "itso",  "status": "pending" | "cleared" | "declined" },
#         { "office": "ierc",  "status": "pending" | "cleared" | "declined" },
#         { "office": "ktto",  "status": "pending" | "cleared" | "declined" },
#       ]
#     }
#
#   Note: RDCO does not have a RecordClearance row — its review is reflected
#   in its assignment and Decision, not in a clearance row.
#
#   Implementation sketch:
#     record = get_object_or_404(Record, pk=record_pk)
#     if not (request.user.is_staff or record.owners.filter(user=request.user).exists()):
#         return Response(status=403)
#     clearances = RecordClearance.objects.filter(record=record)
#     return Response({
#         "pipeline_status": record.pipeline_status,
#         "clearances": [{"office": c.office, "status": c.status} for c in clearances],
#     })
