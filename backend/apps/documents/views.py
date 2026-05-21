from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from core.permissions import IsStaff
from .models import RecordUpload, UploadSlot, UploadReview, RecordFile
from .serializers import RecordUploadSerializer, UploadSlotSerializer, RecordFileSerializer
from .services import create_upload


class UploadSlotListView(generics.ListAPIView):
    """GET /documents/slots/?record_type=<id> -- slots required for a record type."""
    serializer_class   = UploadSlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = UploadSlot.objects.all()
        rt = self.request.query_params.get("record_type")
        if rt:
            qs = qs.filter(record_type_id=rt)
        return qs


class RecordSlotListView(APIView):
    """
    GET /documents/records/<id>/slots/
    Returns all UploadSlots with their upload history for the given record.
    Used by the frontend DocumentsPage to show the combined slot+upload view.
    Response: [ { ...slot fields, uploads: [...] }, ... ]
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .serializers import SlotWithUploadsSerializer
        slots = UploadSlot.objects.all()
        data  = SlotWithUploadsSerializer(slots, many=True, context={"record_id": pk, "request": request}).data
        return Response(data)


class RecordUploadListView(generics.ListAPIView):
    """GET /documents/uploads/?record=<id> -- all uploads for a record."""
    serializer_class   = RecordUploadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        record_id = self.request.query_params.get("record")
        return RecordUpload.objects.filter(record_id=record_id).select_related("slot", "status", "uploaded_by")


class RecordUploadCreateView(APIView):
    """POST /documents/uploads/ -- upload a new version of a document."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        record_id = request.data.get("record")
        slot_id   = request.data.get("slot")
        file      = request.FILES.get("file")

        if not all([record_id, slot_id, file]):
            return Response({"detail": "record, slot, and file are required."}, status=400)

        from apps.records.models import Record
        record = Record.objects.get(pk=record_id)
        slot   = UploadSlot.objects.get(pk=slot_id)
        upload = create_upload(record, slot, file, uploaded_by=request.user)
        # TODO: create AuditEvent(UPLOAD)
        return Response(RecordUploadSerializer(upload).data, status=status.HTTP_201_CREATED)


class RecordUploadDownloadView(APIView):
    """GET /documents/uploads/<id>/download/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        upload = RecordUpload.objects.get(pk=pk)
        # TODO: create AuditEvent(DOWNLOAD)
        return FileResponse(upload.file.open(), as_attachment=True, filename=upload.file.name.split("/")[-1])


class RecordFileListView(generics.ListAPIView):
    """GET /documents/files/?record=<id>"""
    serializer_class   = RecordFileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        record_id = self.request.query_params.get("record")
        return RecordFile.objects.filter(record_id=record_id)


class RecordFileUploadView(APIView):
    """POST /documents/files/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file      = request.FILES.get("file")
        record_id = request.data.get("record")
        if not all([file, record_id]):
            return Response({"detail": "record and file are required."}, status=400)
        record_file = RecordFile.objects.create(
            record_id=record_id,
            file=file,
            filename=file.name,
            uploaded_by=request.user,
        )
        # TODO: create AuditEvent(UPLOAD)
        return Response(RecordFileSerializer(record_file).data, status=status.HTTP_201_CREATED)


class RecordFileDownloadAllView(APIView):
    """GET /documents/files/download-all/?record=<id> -- returns a ZIP of all files."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.utils import build_zip
        from django.http import HttpResponse
        record_id = request.query_params.get("record")
        files = RecordFile.objects.filter(record_id=record_id)
        buffer = build_zip(files)
        response = HttpResponse(buffer, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="record_{record_id}_files.zip"'
        # TODO: create AuditEvent(DOWNLOAD)
        return response
