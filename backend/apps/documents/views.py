from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from core.permissions import IsStaff
from .models import RecordUpload, UploadSlot, UploadStatus, UploadReview, RecordFile, PdfExtraction
from .serializers import RecordUploadSerializer, UploadSlotSerializer, RecordFileSerializer, PdfExtractionSerializer, UploadReviewSerializer
from .services import create_upload, delete_upload
from apps.audit.services import create_audit_event

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class SubmitDocumentView(APIView):
    """
    POST /api/v1/documents/submit/

    Accepts a PDF file upload for a given record + slot.
    Validates format (PDF only) and size (≤ 50 MB), saves the file,
    then queues a background Celery task to extract the PDF text
    without blocking the response.

    Request (multipart/form-data):
        record  — Record PK
        slot    — UploadSlot PK
        file    — PDF file

    Response 201:
        upload      — RecordUpload data
        extraction  — PdfExtraction status record (status: "queued")
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.records.models import Record
        from .tasks import extract_pdf_text

        record_id = request.data.get("record")
        slot_id   = request.data.get("slot")
        file      = request.FILES.get("file")

        # --- Basic presence check ---
        if not all([record_id, slot_id, file]):
            return Response(
                {"detail": "record, slot, and file are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Format validation ---
        file_name = file.name.lower()
        content_type = getattr(file, "content_type", "")
        if not file_name.endswith(".pdf") or "pdf" not in content_type:
            return Response(
                {"detail": "Only PDF files are accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Size validation (50 MB) ---
        if file.size > MAX_PDF_SIZE_BYTES:
            mb = file.size / (1024 * 1024)
            return Response(
                {"detail": f"File size {mb:.1f} MB exceeds the 50 MB limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Persist the upload ---
        try:
            record = Record.objects.get(pk=record_id)
            slot   = UploadSlot.objects.get(pk=slot_id)
        except (Record.DoesNotExist, UploadSlot.DoesNotExist):
            return Response(
                {"detail": "Record or slot not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        upload = create_upload(record, slot, file, uploaded_by=request.user)

        # --- Create extraction tracker and queue the background task ---
        extraction = PdfExtraction.objects.create(upload=upload)
        extract_pdf_text.delay(upload.id)

        return Response(
            {
                "upload":     RecordUploadSerializer(upload, context={"request": request}).data,
                "extraction": PdfExtractionSerializer(extraction).data,
            },
            status=status.HTTP_201_CREATED,
        )


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
        from apps.records.models import Record
        from .serializers import SlotWithUploadsSerializer
        try:
            record = Record.objects.select_related("record_type").get(pk=pk)
        except Record.DoesNotExist:
            return Response({"detail": "Record not found."}, status=status.HTTP_404_NOT_FOUND)
        slots = UploadSlot.objects.filter(record_type=record.record_type)
        data  = SlotWithUploadsSerializer(slots, many=True, context={"record_id": pk, "request": request}).data
        return Response(data)


class RecordUploadListView(generics.ListAPIView):
    """GET /documents/uploads/?record=<id> -- all uploads for a record."""
    serializer_class   = RecordUploadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        record_id = self.request.query_params.get("record")
        return RecordUpload.objects.filter(record_id=record_id).select_related("slot", "status", "uploaded_by")


class UploadReviewCreateView(APIView):
    """
    POST /documents/upload-reviews/

    Staff creates a review on a specific upload, simultaneously updating the
    upload's current status to the chosen UploadStatus.

    Request body:
        upload  — RecordUpload PK
        status  — UploadStatus PK  (e.g. Reviewed, Filed, Approved, Disapproved)
        comment — free-text notes (optional)

    Response 201: UploadReview data
    """
    permission_classes = [IsAuthenticated, IsStaff]

    def post(self, request):
        upload_id  = request.data.get("upload")
        status_id  = request.data.get("status")
        comment    = request.data.get("comment", "")

        if not all([upload_id, status_id]):
            return Response(
                {"detail": "upload and status are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            upload        = RecordUpload.objects.select_related("record").get(pk=upload_id)
            upload_status = UploadStatus.objects.get(pk=status_id)
        except (RecordUpload.DoesNotExist, UploadStatus.DoesNotExist):
            return Response(
                {"detail": "Upload or status not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        review = UploadReview.objects.create(
            upload=upload,
            reviewed_by=request.user,
            status=upload_status,
            comment=comment,
        )

        # Mirror the new status on the upload itself so queries don't need to
        # chase through the review history to find the current status.
        upload.status = upload_status
        upload.save(update_fields=["status"])

        return Response(UploadReviewSerializer(review).data, status=status.HTTP_201_CREATED)


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
        create_audit_event(
            "UPLOAD", request.user, record=record,
            metadata={"slot": slot.name, "filename": file.name, "version": upload.version},
        )
        return Response(RecordUploadSerializer(upload).data, status=status.HTTP_201_CREATED)


class RecordUploadDownloadView(APIView):
    """
    GET /documents/uploads/<id>/download/
    GET /documents/uploads/<id>/download/?inline=true  -- serve for in-browser viewing

    Permission: any record owner OR staff (KTTO, RDCO, ITSO, IERC, Django staff).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from core.permissions import STAFF_ROLES, get_role_name
        try:
            upload = RecordUpload.objects.select_related("record", "slot", "uploaded_by").get(pk=pk)
        except RecordUpload.DoesNotExist:
            return Response({"detail": "Upload not found."}, status=status.HTTP_404_NOT_FOUND)

        is_staff_user = get_role_name(request.user) in STAFF_ROLES
        is_owner      = upload.record.owners.filter(user=request.user).exists()

        if not (is_owner or is_staff_user):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        inline = request.query_params.get("inline", "").lower() in ("1", "true", "yes")

        create_audit_event(
            "DOWNLOAD", request.user, record=upload.record,
            metadata={"upload_id": upload.pk, "slot": upload.slot.name, "version": upload.version},
        )
        filename = upload.file.name.split("/")[-1]
        response = FileResponse(
            upload.file.open(),
            content_type="application/pdf",
            as_attachment=not inline,
            filename=filename,
        )
        if inline:
            response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class RecordFileListView(generics.ListAPIView):
    """GET /documents/files/?record=<id>"""
    serializer_class   = RecordFileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        record_id = self.request.query_params.get("record")
        return RecordFile.objects.filter(record_id=record_id)


class RecordFileUploadView(APIView):
    """
    POST /documents/files/upload/
    Staff only — attach any supplementary file to a record.
    Owners submit PDFs through the slot-based SubmitDocumentView instead.
    """
    permission_classes = [IsAuthenticated, IsStaff]

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
        create_audit_event(
            "UPLOAD", request.user, record=record_file.record,
            metadata={"filename": file.name},
        )
        return Response(RecordFileSerializer(record_file).data, status=status.HTTP_201_CREATED)


class RecordUploadDeleteView(APIView):
    """
    DELETE /documents/uploads/<id>/
    Owners may delete any version > 1.  Staff may delete any version (force=True).
    The physical file is removed from storage before the DB row is deleted.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            upload = RecordUpload.objects.select_related("record", "slot").get(pk=pk)
        except RecordUpload.DoesNotExist:
            return Response({"detail": "Upload not found."}, status=status.HTTP_404_NOT_FOUND)

        # Permission: owner or staff
        from core.permissions import STAFF_ROLES, get_role_name
        is_staff_user = get_role_name(request.user) in STAFF_ROLES
        is_owner = upload.record.owners.filter(user=request.user).exists()

        if not (is_owner or is_staff_user):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        try:
            delete_upload(upload, deleted_by=request.user, force=is_staff_user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        create_audit_event(
            "DELETE", request.user, record=upload.record,
            metadata={"upload_id": pk, "slot": upload.slot.name, "version": upload.version},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecordFileDownloadView(APIView):
    """
    GET /documents/files/<id>/download/
    GET /documents/files/<id>/download/?inline=true  -- serve for in-browser viewing

    Permission: any record owner OR staff.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from core.permissions import STAFF_ROLES, get_role_name
        try:
            record_file = RecordFile.objects.select_related("record").get(pk=pk)
        except RecordFile.DoesNotExist:
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)

        is_staff_user = get_role_name(request.user) in STAFF_ROLES
        is_owner      = record_file.record.owners.filter(user=request.user).exists()

        if not (is_owner or is_staff_user):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        inline = request.query_params.get("inline", "").lower() in ("1", "true", "yes")
        filename = record_file.filename or record_file.file.name.split("/")[-1]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = "application/pdf" if ext == "pdf" else "application/octet-stream"

        create_audit_event(
            "DOWNLOAD", request.user, record=record_file.record,
            metadata={"file_id": pk, "filename": filename},
        )
        response = FileResponse(
            record_file.file.open(),
            content_type=content_type,
            as_attachment=not inline,
            filename=filename,
        )
        if inline and ext == "pdf":
            response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class RecordFileDeleteView(APIView):
    """
    DELETE /documents/files/<id>/
    Owners and staff may delete a RecordFile attachment.
    Physical file is removed from storage.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        from .models import RecordFile
        try:
            record_file = RecordFile.objects.select_related("record").get(pk=pk)
        except RecordFile.DoesNotExist:
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)

        from core.permissions import STAFF_ROLES, get_role_name
        is_staff_user = get_role_name(request.user) in STAFF_ROLES
        is_owner = record_file.record.owners.filter(user=request.user).exists()

        if not (is_owner or is_staff_user):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        record = record_file.record
        filename = record_file.filename

        try:
            if record_file.file:
                record_file.file.delete(save=False)
        except Exception:
            pass

        record_file.delete()

        create_audit_event(
            "DELETE", request.user, record=record,
            metadata={"filename": filename},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        from apps.records.models import Record as RecordModel
        try:
            record_obj = RecordModel.objects.get(pk=record_id)
        except RecordModel.DoesNotExist:
            record_obj = None
        create_audit_event(
            "DOWNLOAD", request.user, record=record_obj,
            metadata={"record_id": record_id, "file_count": files.count()},
        )
        return response
