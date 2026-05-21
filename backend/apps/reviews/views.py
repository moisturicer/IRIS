from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsReviewer
from .models import Review, RecordAuthPin
from .serializers import ReviewSerializer, ReviewWriteSerializer, RecordAuthPinSerializer
from .services import approve_record, decline_record, resubmit_record
from apps.records.models import Record


class ReviewViewSet(viewsets.GenericViewSet):
    """
    GET  /reviews/pending/    -- role-filtered pending records queue
    POST /reviews/            -- submit a review (approve or decline)
    GET  /reviews/approved/   -- records I approved
    GET  /reviews/declined/   -- records I declined
    """
    permission_classes = [IsAuthenticated, IsReviewer]

    def get_queryset(self):
        return Review.objects.filter(reviewed_by=self.request.user).select_related("record")

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Return records pending review at the current user's stage."""
        role_name = request.user.role.name if request.user.role else ""
        stage_map = {
            "Adviser": "adviser_review",
            "KTTO":    "ktto_review",
            "TBI":     "ktto_review",
            "RDCO":    "rdco_review",
        }
        pipeline_status = stage_map.get(role_name)
        if not pipeline_status:
            return Response([])

        records = Record.objects.filter(pipeline_status=pipeline_status).select_related(
            "classification", "record_type"
        )
        from apps.records.serializers import RecordListSerializer
        return Response(RecordListSerializer(records, many=True, context={"request": request}).data)

    @action(detail=False, methods=["post"])
    def submit(self, request):
        """POST /reviews/submit/ -- body: {record_id, status, comment}"""
        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        record = Record.objects.get(pk=data["record_id"])
        if data["status"] == "approved":
            review = approve_record(record, reviewed_by=request.user, comment=data.get("comment", ""))
        else:
            review = decline_record(record, reviewed_by=request.user, comment=data.get("comment", ""))

        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def resubmit(self, request):
        """POST /reviews/resubmit/ -- body: {record_id} -- student resubmits declined record."""
        record = Record.objects.get(pk=request.data.get("record_id"))
        resubmit_record(record, submitted_by=request.user)
        return Response({"detail": "Record resubmitted."})

    @action(detail=False, methods=["get"])
    def approved(self, request):
        reviews  = Review.objects.filter(reviewed_by=request.user, status="approved")
        from apps.records.serializers import RecordListSerializer
        records = [r.record for r in reviews]
        return Response(RecordListSerializer(records, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"])
    def declined(self, request):
        reviews = Review.objects.filter(reviewed_by=request.user, status="declined")
        from apps.records.serializers import RecordListSerializer
        records = [r.record for r in reviews]
        return Response(RecordListSerializer(records, many=True, context={"request": request}).data)


class RecordAuthPinViewSet(viewsets.GenericViewSet):
    """
    POST /reviews/pin/generate/  -- generate + email a PIN for a record
    POST /reviews/pin/verify/    -- verify PIN and unlock access
    TODO: implement pin generation and verification using core.utils.generate_pin
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        return Response({"detail": "TODO: implement PIN generation"})

    @action(detail=False, methods=["post"])
    def verify(self, request):
        return Response({"detail": "TODO: implement PIN verification"})
