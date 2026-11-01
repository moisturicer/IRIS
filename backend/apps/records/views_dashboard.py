from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Record
from apps.reviews.models import ResubmissionRequest
from core.enums import (
    DELETE_REVIEW_STATUSES,
    PUBLICLY_VISIBLE_STATUSES,
    PipelineStatus,
    ResubmissionRequestState,
    WorkflowState,
)

#: The statuses that mean "somebody is still reviewing this". One since
#: ADR-032: whoever holds a record, it is stored `in_review` (IR-260). The five
#: fixed-pipeline stages it replaced were deleted by IR-274.
IN_REVIEW_STATUSES = (PipelineStatus.IN_REVIEW,)

#: The derived states that wait on the owner rather than a reviewer (IR-534,
#: spec Appendix D · B2): a reviewer asked for a revision, or for a document.
NEEDS_OWNER_ACTION = frozenset({
    WorkflowState.AWAITING_RESUBMISSION.value,
    WorkflowState.AWAITING_DOCUMENT.value,
})


def needs_action_count(user) -> int:
    """
    How many of `user`'s own records are waiting on them -- what the My
    Library dot reads. The state is the tracker's own derivation
    (`tracker.workflow_facts`), not a second rule: a record counts exactly
    when My Library would show it as awaiting a resubmission or a document.
    Only records in review can be in either state, so only those are read.
    """
    from apps.reviews.tracker import workflow_facts

    in_review = (
        Record.objects.filter(owners__user=user, pipeline_status__in=IN_REVIEW_STATUSES)
        .distinct().select_related("record_type")
    )
    return sum(
        1 for facts in workflow_facts(in_review).values()
        if facts["workflow_state"] in NEEDS_OWNER_ACTION
    )


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
            # What is waiting on the owner (B2): the sidebar's My Library dot.
            # Unlike `pending_mine`, which is "in review", this is actionable.
            "needs_action_mine": needs_action_count(user),
            # Staff-only totals -- return 0 for students
            "total_published":  Record.objects.filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES).count() if request.user.role else 0,
        })
