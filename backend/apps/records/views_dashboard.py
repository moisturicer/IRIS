from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import ADMIN_ROLES, REVIEWER_ROLES, IsCommentModerator, get_role_name
from .models import DeleteRequest, DownloadRequest, Record
from apps.reviews.models import ResubmissionRequest
from core.enums import (
    DELETE_REVIEW_STATUSES,
    PUBLICLY_VISIBLE_STATUSES,
    PipelineStatus,
    RequestStatus,
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


def reviews_waiting(user) -> int:
    """My Reviews' To review count, or 0 for a role that reviews nothing."""
    if get_role_name(user) not in REVIEWER_ROLES:
        return 0
    from apps.reviews.my_reviews import waiting_count
    return waiting_count(user)


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
            # Reviews waiting on the user: the sidebar's My Reviews badge
            # (IR-1208), the same number as My Reviews' To review tab.
            "reviews_waiting_mine": reviews_waiting(user),
            # Staff-only totals -- return 0 for students
            "total_published":  Record.objects.filter(pipeline_status__in=PUBLICLY_VISIBLE_STATUSES).count() if request.user.role else 0,
        })


class QueueCountsView(APIView):
    """
    GET /dashboard/queue-counts/ -- RDCO and the System Admin (IR-1138, IR-691).

    How many requests wait in each queue the caller works, for the sidebar's
    counts. Role requests are counted as the Role Requests queue lists them:
    verified accounts only (ADR-051 decision 22). `reported_comments` counts
    the comments with an open report, the queue both roles share (decision
    2026-11-15); it is all the System Admin is told.
    """
    permission_classes = [IsAuthenticated, IsCommentModerator]

    def get(self, request):
        from apps.accounts.models import RoleRequest
        from .comment_moderation import reported as reported_comments

        reported = reported_comments(request.user).count()
        if get_role_name(request.user) not in ADMIN_ROLES:
            return Response({"reported_comments": reported})
        return Response({
            "reported_comments": reported,
            "download_requests": DownloadRequest.objects.filter(status=RequestStatus.PENDING).count(),
            "delete_requests": DeleteRequest.objects.filter(status=RequestStatus.PENDING).count(),
            "role_change_requests": RoleRequest.objects.filter(
                status=RequestStatus.PENDING, user__is_verified=True
            ).count(),
        })
