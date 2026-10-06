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
    #: Whether the viewer may remove this file -- the delete view's own rule
    #: (IR-476), so Paper View offers Remove only where it would succeed.
    can_remove       = serializers.SerializerMethodField()

    class Meta:
        model  = RecordFile
        fields = [
            "id", "record", "file", "filename", "uploaded_by", "uploaded_by_name",
            "created_at", "can_remove",
        ]
        read_only_fields = ["uploaded_by", "uploaded_by_name"]

    def get_can_remove(self, obj):
        from .attachments import may_remove, removable_parties

        user = getattr(self.context.get("request"), "user", None)
        # One set per record, shared by every file in a list.
        cache = self.context.setdefault("_removable_parties", {})
        if obj.record_id not in cache:
            cache[obj.record_id] = removable_parties(obj.record, user)
        return may_remove(obj, user, removable=cache[obj.record_id])

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip() or obj.uploaded_by.email
        return None


class PdfExtractionSerializer(serializers.ModelSerializer):
    """Extraction status, not extraction output.

    `structure` is deliberately absent: it is the chunker's input and can run
    to megabytes on a thesis, which is not something to attach to every
    upload response. `content_hash` is absent too — it is an internal
    idempotency key with no client that needs it. `extractor` is present
    because "what produced this?" is the question an operator asks about a
    bad extraction, and the ticket asks for it to be observable.
    """
    class Meta:
        model  = PdfExtraction
        fields = [
            "id", "upload", "status", "extractor",
            "celery_task_id", "error", "created_at", "completed_at",
        ]
        read_only_fields = fields
