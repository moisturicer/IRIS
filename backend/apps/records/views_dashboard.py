from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from core.permissions import IsStaff
from .models import Record, Classification, PSCEDClassification


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
            "pending_mine":     Record.objects.filter(pk__in=my_ids, pipeline_status__in=["adviser_review","ktto_review","rdco_review"]).count(),
            "approved_mine":    Record.objects.filter(pk__in=my_ids, pipeline_status="published").count(),
            "declined_mine":    Record.objects.filter(pk__in=my_ids, pipeline_status="declined").count(),
            # Staff-only totals -- return 0 for students
            "total_published":  Record.objects.filter(pipeline_status="published").count() if request.user.role else 0,
        })


class ClassificationChartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = (
            Record.objects.filter(pipeline_status="published")
            .values("classification__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return Response(list(data))


class PSCEDChartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = (
            Record.objects.filter(pipeline_status="published")
            .values("psced__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return Response(list(data))
