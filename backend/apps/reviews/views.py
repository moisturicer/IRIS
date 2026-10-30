from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.permissions import IsReviewer, IsStaff
from .models import Review


class ReviewViewSet(viewsets.GenericViewSet):
    """
    POST /reviews/submit/     -- retired fixed-stage action (410)
    POST /reviews/resubmit/   -- retired fixed-stage resubmission (410)
    GET  /reviews/analytics/  -- workflow analytics, scoped by office (IR-626)
    """
    permission_classes = [IsAuthenticated, IsReviewer]

    # The three queue lists (`pending/`, `approved/`, `declined/`) were
    # replaced by My Reviews, `MyReviewsView` below (IR-268).

    def get_permissions(self):
        # resubmit is called by record owners (students), not reviewers
        if self.action == "resubmit":
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        return Review.objects.filter(reviewed_by=self.request.user).select_related("record")

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, IsStaff])
    def analytics(self, request):
        """
        GET /reviews/analytics/?office=&from=&to=  -- workflow analytics (IR-626)

        Computed from the workflow audit log (`apps/reviews/analytics.py`). An
        office reads its own figures and RDCO every party's; naming another
        office is refused with 403.
        """
        from . import analytics

        try:
            payload = analytics.workflow_analytics(request.user, request.query_params)
        except analytics.AnalyticsRefused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except analytics.AnalyticsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @action(detail=False, methods=["post"])
    def submit(self, request):
        return Response(
            {"detail": "The fixed-stage review form is retired. Use the record's review actions."},
            status=status.HTTP_410_GONE,
        )

    @action(detail=False, methods=["post"])
    def resubmit(self, request):
        return Response(
            {"detail": "Use the record's Submit new version action for a requested revision."},
            status=status.HTTP_410_GONE,
        )

class MyReviewsView(APIView):
    """
    GET /reviews/mine/?tab=&outcome=&office=&cursor=&sort=&overdue=  -- My Reviews (IR-268, IR-622)

    A reviewer's own seats plus their office's pool, one tab at a time, with
    every tab's count (ADR-032 §9 and its 2026-10-08 Amendment). `office` is a
    coordinator's view of their own office: anyone else naming one is refused
    with 403. Any signed-in user may ask; someone with no review work gets
    empty tabs.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from . import my_reviews

        params = request.query_params
        try:
            payload = my_reviews.my_reviews(
                request.user,
                tab=params.get("tab"),
                outcome=params.get("outcome"),
                office=params.get("office"),
                cursor=params.get("cursor"),
                sort=params.get("sort"),
                overdue=params.get("overdue"),
            )
        except my_reviews.MyReviewsRefused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except my_reviews.MyReviewsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class OfficeConsoleView(APIView):
    """
    GET /reviews/office/?office=  -- the coordinator console (IR-623)

    One office's open seats, unclaimed pool and per-member load. `office`
    defaults to the office the caller coordinates; anyone who does not
    coordinate the office asked for is refused with 403.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .office_console import ConsoleRefused, office_console

        try:
            payload = office_console(request.user, office=request.query_params.get("office"))
        except ConsoleRefused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(payload)
