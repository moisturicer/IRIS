from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from core.permissions import IsOwnerOrStaff, IsReviewer, IsStaff
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

    @action(detail=False, methods=["post"])
    def import_excel(self, request):
        """POST /records/import/ -- bulk import from .xls/.xlsx."""
        # TODO: call parse_excel_import(request.FILES["file"])
        return Response({"detail": "TODO: implement Excel import"})

    @action(detail=False, methods=["get"])
    def download_template(self, request):
        """GET /records/download_template/ -- return the import template file."""
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
    GET    /download-requests/         -- admin: all pending
    POST   /download-requests/         -- user requests download
    PATCH  /download-requests/<id>/    -- admin: approve/decline
    TODO: restrict list to IsStaff, restrict create to IsAuthenticated
    """
    serializer_class = DownloadRequestSerializer
    queryset         = DownloadRequest.objects.select_related("record", "requested_by")


class DeleteRequestViewSet(viewsets.ModelViewSet):
    """
    GET    /delete-requests/
    PATCH  /delete-requests/<id>/   -- admin approve triggers actual soft delete
    TODO: on approve call soft_delete_record and update Record.pipeline_status
    """
    serializer_class = DeleteRequestSerializer
    queryset         = DeleteRequest.objects.select_related("record", "requested_by")
