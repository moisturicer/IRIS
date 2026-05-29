from rest_framework import serializers
from .models import RecordUpload, UploadSlot, UploadStatus, UploadReview, RecordFile, PdfExtraction


class UploadSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UploadSlot
        fields = ["id", "name", "record_type", "is_required"]


class UploadStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UploadStatus
        fields = ["id", "name"]


class UploadReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True)

    class Meta:
        model  = UploadReview
        fields = ["id", "upload", "reviewed_by", "reviewer_name", "status", "comment", "created_at"]


class RecordUploadSerializer(serializers.ModelSerializer):
    slot_name        = serializers.CharField(source="slot.name", read_only=True)
    status_name      = serializers.CharField(source="status.name", read_only=True, default=None)
    uploaded_by_name = serializers.SerializerMethodField()
    reviews          = UploadReviewSerializer(many=True, read_only=True)

    class Meta:
        model  = RecordUpload
        fields = [
            "id", "record", "slot", "slot_name", "file", "version",
            "status", "status_name", "uploaded_by", "uploaded_by_name",
            "created_at", "reviews",
        ]
        read_only_fields = ["version", "uploaded_by"]

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.username
        return None


class SlotWithUploadsSerializer(serializers.ModelSerializer):
    """
    UploadSlot serializer that embeds all uploads for a specific record.
    The record_id is passed via serializer context.
    """
    uploads = serializers.SerializerMethodField()

    class Meta:
        model  = UploadSlot
        fields = ["id", "name", "record_type", "is_required", "uploads"]

    def get_uploads(self, slot):
        record_id = self.context.get("record_id")
        request   = self.context.get("request")
        if not record_id:
            return []
        uploads = RecordUpload.objects.filter(
            slot=slot, record_id=record_id
        ).select_related("uploaded_by").order_by("-version")
        return RecordUploadSerializer(uploads, many=True, context={"request": request}).data


class RecordFileSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = RecordFile
        fields = ["id", "record", "file", "filename", "uploaded_by", "uploaded_by_name", "created_at"]
        read_only_fields = ["uploaded_by", "uploaded_by_name"]

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.email
        return None


class PdfExtractionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PdfExtraction
        fields = ["id", "upload", "status", "celery_task_id", "error", "created_at", "completed_at"]
        read_only_fields = fields
