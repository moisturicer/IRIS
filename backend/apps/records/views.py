from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
import jwt

from core.permissions import IsOwnerOrStaff, IsReviewer, IsStaff, IsAdmin
from .download_tokens import make_download_token, verify_download_token
from .download_service import file_response_for_record
from .models import Record, DownloadRequest, DeleteRequest
from .serializers import (
    RecordListSerializer,
    RecordDetailSerializer,
    RecordWriteSerializer,
    DownloadRequestSerializer,
    DeleteRequestSerializer,
)
from .filters import RecordFilter
from .services import soft_delete_record, parse_excel_import


class RecordViewSet(viewsets.ModelViewSet):
    """
    GET    /records/           -- published records (anyone authenticated)
    POST   /records/           -- create (student/adviser+)
    GET    /records/<id>/      -- detail
    PATCH  /records/<id>/      -- update (owner only, not yet approved)
    DELETE /records/<id>/      -- soft delete / create DeleteRequest
    """
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class  = RecordFilter
    search_fields    = ["title", "abstract", "authors__name"]
    ordering_fields  = ["created_at", "year_accomplished", "title", "access_count"]
    ordering         = ["-created_at"]

    def get_queryset(self):
        # Public list shows only published records
        if self.action == "list":
            return Record.objects.filter(pipeline_status="published").select_related(
                "classification", "psced", "record_type", "adviser"
            ).prefetch_related("owners__user", "authors")
        return Record.objects.select_related(
            "classification", "psced", "record_type", "adviser"
        ).prefetch_related("owners__user", "authors")

    def get_serializer_class(self):
        if self.action == "list":
            return RecordListSerializer
        if self.action in ("create", "update", "partial_update"):
            return RecordWriteSerializer
        return RecordDetailSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsOwnerOrStaff()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        from .models import RecordOwner
        record = serializer.save(added_by=self.request.user, pipeline_status="draft")
        # Add the creator as the primary owner automatically
        RecordOwner.objects.create(record=record, user=self.request.user, is_primary=True)
        # TODO: trigger notify_new_record(record, request.user)

    def perform_destroy(self, instance):
        # Approved records go through delete request flow
        if instance.pipeline_status == "published":
            DeleteRequest.objects.create(record=instance, requested_by=self.request.user)
            instance.pipeline_status = "pending_delete"
            instance.save(update_fields=["pipeline_status"])
        else:
            soft_delete_record(instance, deleted_by=self.request.user)

    @action(detail=True, methods=["post"])
    def increment_access(self, request, pk=None):
        """POST /records/<id>/increment_access/"""
        record = self.get_object()
        Record.objects.filter(pk=record.pk).update(access_count=record.access_count + 1)
        # TODO: create AuditEvent(ACCESS) here
        return Response({"access_count": record.access_count + 1})

    @action(detail=True, methods=["patch"], permission_classes=[IsReviewer])
    def tags(self, request, pk=None):
        """PATCH /records/<id>/tags/ -- update IP/commercialization/community flags."""
        record = self.get_object()
        # TODO: validate and update is_ip, for_commercialization, community_extension
        return Response({"detail": "TODO: implement tag update"})

    @action(detail=False, methods=["get"])
    def mine(self, request):
        """GET /records/mine/ -- records the current user owns."""
        qs = Record.objects.filter(owners__user=request.user).distinct()
        serializer = RecordListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated, IsStaff])
    def import_excel(self, request):
        """POST /records/import/ -- bulk import from .xls/.xlsx. Staff only."""
        # TODO: call parse_excel_import(request.FILES["file"])
        return Response({"detail": "TODO: implement Excel import"})

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated, IsStaff])
    def download_template(self, request):
        """GET /records/download_template/ -- return the import template file. Staff only."""
        # TODO: return FileResponse of the template .xlsx
        return Response({"detail": "TODO: implement template download"})


class MyRecordsViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET /records/mine/          -- list records I own (with pipeline_status)
    GET /records/mine/<id>/     -- detail with full review history
    """
    serializer_class = RecordDetailSerializer

    def get_queryset(self):
        return Record.objects.filter(owners__user=self.request.user).distinct()


class DownloadRequestViewSet(viewsets.ModelViewSet):
    """
    GET    /download-requests/         -- staff only: view all pending requests
    POST   /download-requests/         -- any authenticated user: request a download
    PATCH  /download-requests/<id>/    -- staff only: approve or decline
    DELETE /download-requests/<id>/    -- admin only
    """
    serializer_class = DownloadRequestSerializer
    queryset         = DownloadRequest.objects.select_related("record", "requested_by")
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action == "create":
            # Any logged-in user may request a download
            return [IsAuthenticated()]
        if self.action == "destroy":
            # Only admins may delete a download request record
            return [IsAuthenticated(), IsAdmin()]
        # list, retrieve, update, partial_update → staff only
        return [IsAuthenticated(), IsStaff()]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by("-created_at")

    def perform_create(self, serializer):
        record = serializer.validated_data["record"]
        user   = self.request.user
        if DownloadRequest.objects.filter(
            record=record, requested_by=user, status="pending"
        ).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                {"record": ["You already have a pending download request for this record."]}
            )
        serializer.save(requested_by=user)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        action = request.data.get("action")
        if action not in ("approve", "decline"):
            return Response(
                {"detail": "Provide action: 'approve' or 'decline'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if instance.status != "pending":
            return Response(
                {"detail": "This request has already been reviewed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.reviewed_by = request.user
        instance.reviewed_at = timezone.now()
        instance.status = "approved" if action == "approve" else "declined"
        instance.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        data = self.get_serializer(instance).data
        if action == "approve":
            token = make_download_token(
                download_request_id=instance.id,
                record_id=instance.record_id,
                user_id=instance.requested_by_id,
            )
            data["download_url"] = f"{settings.FRONTEND_URL.rstrip('/')}/download?token={token}"
        return Response(data)


class DownloadRedeemView(APIView):
    """
    GET /records/download/?token=<jwt>
    Redeem an approved download JWT and stream the record PDF.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response({"detail": "token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            claims = verify_download_token(token)
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Download link has expired."}, status=status.HTTP_403_FORBIDDEN)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid download link."}, status=status.HTTP_403_FORBIDDEN)

        try:
            dl_request = DownloadRequest.objects.select_related("record").get(
                pk=claims["drid"], status="approved"
            )
        except DownloadRequest.DoesNotExist:
            return Response({"detail": "Download request not found or not approved."}, status=404)

        if dl_request.record_id != claims["rid"] or dl_request.requested_by_id != claims["uid"]:
            return Response({"detail": "Invalid download link."}, status=status.HTTP_403_FORBIDDEN)

        response = file_response_for_record(dl_request.record)
        if not response:
            return Response(
                {"detail": "No downloadable file is available for this record."},
                status=status.HTTP_404_NOT_FOUND,
            )
        # TODO(SRS): apply per-user watermark (email, date) before streaming when required
        return response


class DeleteRequestViewSet(viewsets.ModelViewSet):
    """
    GET    /delete-requests/           -- admin only: all pending delete requests
    PATCH  /delete-requests/<id>/      -- admin only: approve triggers soft delete
    """
    serializer_class = DeleteRequestSerializer
    queryset         = DeleteRequest.objects.select_related("record", "requested_by")
    # All actions on delete requests are restricted to admins
    permission_classes = [IsAuthenticated, IsAdmin]
