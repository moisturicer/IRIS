from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.permissions import IsReviewer, IsStaff
from core.exceptions import InvalidPipelineTransition
from apps.records import lifecycle
from core.enums import ReviewDecision
from .models import Review, RecordAuthPin
from .serializers import ReviewSerializer, ReviewWriteSerializer
from .services import (
    approve_record, decline_record, reject_record,
    resubmit_record, submit_clearance,
    ROLE_TO_OFFICE,
)
from apps.records.models import Record
from apps.audit.services import create_audit_event

PIN_EXPIRY_HOURS = 24


class ReviewViewSet(viewsets.GenericViewSet):
    """
    POST /reviews/submit/     -- submit a review or clearance decision
    POST /reviews/resubmit/   -- owner resubmits a declined record

    The three queue lists (`pending/`, `approved/`, `declined/`) were replaced
    by My Reviews, `MyReviewsView` below (IR-268).
    GET  /reviews/analytics/  -- per-stage average processing time (TODO stub, 501)
    """
    permission_classes = [IsAuthenticated, IsReviewer]

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
        GET /reviews/analytics/

        TODO (M07 — FR-M7-01): implement per-stage average processing time.
        For each Review.stage, compute the average elapsed days between consecutive
        Review.created_at timestamps on the same record (ordered by created_at).
        Exclude records still in a stage (no subsequent review entry yet).
        Return: { stage_averages: [{ stage, avg_days, record_count }] }
        Permission: IsAuthenticated + IsStaff
        """
        return Response({"detail": "Analytics not yet implemented."}, status=status.HTTP_501_NOT_IMPLEMENTED)

    @action(detail=False, methods=["post"])
    def submit(self, request):
        """
        POST /reviews/submit/

        Body: { "record_id": <int>, "status": "approved"|"declined"|"rejected", "comment": "<str>" }

        Routing:
          • Sequential stages (adviser_review, rdco_intake, rdco_review):
              approved  → advance to next stage (rdco_intake also creates office clearances)
              declined  → record enters 'declined'; the owner may resubmit
              rejected  → terminal; record enters 'rejected'. adviser_review and
                          rdco_review only -- refused with 400 at rdco_intake (IR-265)
          • Clearance stages (itso_review, parallel_review):
              Routes to submit_clearance; office determined from user's role.
              approved  → clears office; advances pipeline when all offices are cleared.
              declined  → record enters 'declined' (same as above).
              rejected  → refused with 400; an office cannot reject (IR-265).
        """
        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            record = Record.objects.select_related("record_type", "adviser").get(
                pk=data["record_id"]
            )
        except Record.DoesNotExist:
            return Response({"detail": "Record not found."}, status=status.HTTP_404_NOT_FOUND)

        decision = data["status"]
        comment  = data.get("comment", "")

        try:
            if lifecycle.is_clearance_stage(record.pipeline_status):
                # Clearance stage — office is inferred from the reviewer's role
                role_name = request.user.role.name if request.user.role else ""
                office    = ROLE_TO_OFFICE.get(role_name, "")
                review = submit_clearance(
                    record, reviewed_by=request.user,
                    office=office, decision=decision, comment=comment,
                )
            else:
                # Sequential stage
                if decision == ReviewDecision.APPROVED:
                    review = approve_record(record, reviewed_by=request.user, comment=comment)
                elif decision == ReviewDecision.REJECTED:
                    review = reject_record(record, reviewed_by=request.user, comment=comment)
                else:
                    review = decline_record(record, reviewed_by=request.user, comment=comment)

        except InvalidPipelineTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def resubmit(self, request):
        """
        POST /reviews/resubmit/

        Body: { "record_id": <int> }

        Owner resubmits a declined record. Clears all office clearances and routes
        to the correct first stage based on record type.
        Only the record owner or staff may call this.
        """
        record_id = request.data.get("record_id")
        if not record_id:
            return Response({"detail": "record_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            record = Record.objects.select_related("record_type", "adviser").get(pk=record_id)
        except Record.DoesNotExist:
            return Response({"detail": "Record not found."}, status=status.HTTP_404_NOT_FOUND)

        from core.permissions import owns_or_staffs_record
        if not owns_or_staffs_record(request.user, record):
            return Response(
                {"detail": "Only the record owner may resubmit."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            resubmit_record(record, submitted_by=request.user)
        except InvalidPipelineTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Record resubmitted successfully."})


class MyReviewsView(APIView):
    """
    GET /reviews/mine/?tab=&outcome=&office=&cursor=  -- My Reviews (IR-268)

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
            )
        except my_reviews.MyReviewsRefused as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except my_reviews.MyReviewsError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class RecordAuthPinViewSet(viewsets.GenericViewSet):
    """
    POST /reviews/pin/generate/  -- issue a one-time PIN and email it to the requester
    POST /reviews/pin/verify/    -- consume the PIN and confirm access

    PINs expire after PIN_EXPIRY_HOURS (24 h) and can only be used once.
    A rejected, used, or expired PIN returns "Invalid or already used PIN"
    (identical error for security — no detail disclosed).
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """
        Body: { "record_id": <int> }
        Creates a single-use PIN tied to the requesting user, sets an expiry
        24 hours from now, invalidates any previous unused PINs, and emails the PIN.
        """
        record_id = request.data.get("record_id")
        if not record_id:
            return Response({"detail": "record_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            record = Record.objects.get(pk=record_id)
        except Record.DoesNotExist:
            return Response({"detail": "Record not found."}, status=status.HTTP_404_NOT_FOUND)

        # Invalidate any outstanding unused PINs for this user+record pair
        RecordAuthPin.objects.filter(
            record=record, user=request.user, is_used=False
        ).update(is_used=True)

        from core.utils import generate_pin, send_email_async
        pin        = generate_pin(length=6)
        expires_at = timezone.now() + timedelta(hours=PIN_EXPIRY_HOURS)

        RecordAuthPin.objects.create(
            record=record,
            user=request.user,
            email=request.user.email,
            pin=pin,
            expires_at=expires_at,
        )

        send_email_async(
            subject=f"[IRIS] Your access PIN for: {record.title[:60]}",
            message=(
                f"Hello {request.user.first_name},\n\n"
                f"Your one-time access PIN for the record below is:\n\n"
                f"    {pin}\n\n"
                f'Record: "{record.title}"\n\n'
                f"This PIN expires in {PIN_EXPIRY_HOURS} hours and is single-use. "
                f"Do not share it.\n\n"
                f"— The IRIS Team"
            ),
            recipient_list=[request.user.email],
        )

        create_audit_event("PIN_GENERATED", request.user, record=record, metadata={"record_id": record.pk})

        return Response(
            {"detail": f"Access PIN sent to your email address. It expires in {PIN_EXPIRY_HOURS} hours."},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def verify(self, request):
        """
        Body: { "record_id": <int>, "pin": "<str>" }

        Verifies the PIN:
          - Must be unused (is_used = False)
          - Must not be expired (expires_at > now())
        Marks the PIN as used on success. Returns { "verified": true, "record_id": <int> }.
        """
        record_id = request.data.get("record_id")
        pin       = str(request.data.get("pin", "")).strip().upper()

        if not record_id or not pin:
            return Response(
                {"detail": "record_id and pin are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        auth_pin = RecordAuthPin.objects.filter(
            record_id=record_id,
            user=request.user,
            pin=pin,
            is_used=False,
        ).first()

        # Reject if not found, already used, or expired
        if not auth_pin or (auth_pin.expires_at and auth_pin.expires_at < timezone.now()):
            return Response(
                {"detail": "Invalid or already used PIN."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        auth_pin.is_used = True
        auth_pin.save(update_fields=["is_used"])

        create_audit_event("PIN_VERIFIED", request.user, record=auth_pin.record, metadata={"record_id": int(record_id)})

        return Response({"verified": True, "record_id": int(record_id)})
