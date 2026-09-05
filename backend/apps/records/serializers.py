from rest_framework import serializers
from .models import (
    Record, RecordOwner, Author, DownloadRequest, DeleteRequest,
    Classification, PSCEDClassification, RecordType,
)


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Author
        fields = ["id", "name", "role"]


class RecordOwnerSerializer(serializers.ModelSerializer):
    email      = serializers.CharField(source="user.email", read_only=True)
    full_name  = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model  = RecordOwner
        fields = ["id", "user", "email", "full_name", "is_primary"]


class RecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views and DataTable."""
    classification_name = serializers.CharField(source="classification.name", read_only=True)
    record_type_name    = serializers.CharField(source="record_type.name", read_only=True)
    authors             = AuthorSerializer(many=True, read_only=True)
    # Annotated by RecordViewSet.get_queryset; 0 when the queryset omits it.
    file_count          = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model  = Record
        fields = [
            "id", "title", "abstract", "year_accomplished", "classification_name",
            "record_type_name", "pipeline_status", "is_ip", "ip_type",
            "for_commercialization", "community_extension",
            "access_count", "file_count", "created_at", "authors",
        ]


class RecordDetailSerializer(serializers.ModelSerializer):
    """Full record detail including all related objects."""
    owners         = RecordOwnerSerializer(many=True, read_only=True)
    authors        = AuthorSerializer(many=True, read_only=True)
    classification = serializers.StringRelatedField()
    psced          = serializers.StringRelatedField()
    record_type    = serializers.StringRelatedField()
    # Mirrored from RecordListSerializer so the detail payload is a strict
    # superset of the list payload — the frontend types RecordDetail as an
    # extension of RecordListItem and reads these on the paper view.
    classification_name = serializers.CharField(source="classification.name", read_only=True)
    record_type_name    = serializers.CharField(source="record_type.name", read_only=True)
    file_count          = serializers.SerializerMethodField()
    reviews        = serializers.SerializerMethodField()
    clearances     = serializers.SerializerMethodField()
    files          = serializers.SerializerMethodField()

    def get_reviews(self, obj):
        from apps.reviews.models import Review
        qs = (
            Review.objects
            .filter(record=obj)
            .select_related("reviewed_by")
            .order_by("created_at")
        )
        return [
            {
                "id":               r.id,
                "stage":            r.stage,
                "status":           r.status,
                "comment":          r.comment,
                "reviewed_by_name": r.reviewed_by.get_full_name() if r.reviewed_by else None,
                "created_at":       r.created_at.isoformat(),
            }
            for r in qs
        ]

    def get_clearances(self, obj):
        """
        Per-office clearance state. This is what makes clearance-aware
        resubmission visible: a preserved clearance shows as cleared with a
        decision date earlier than the current submission.
        """
        return [
            {
                "office":           c.office,
                "office_label":     c.get_office_display(),
                "status":           c.status,
                "comment":          c.comment,
                "reviewed_by_name": c.reviewed_by.get_full_name() if c.reviewed_by else None,
                "updated_at":       c.updated_at.isoformat(),
            }
            for c in obj.clearances.select_related("reviewed_by").order_by("office")
        ]

    def get_file_count(self, obj):
        return obj.files.count()

    def get_files(self, obj):
        return [
            {
                "id":          f.id,
                "filename":    f.filename,
                "url":         f.file.url if f.file else None,
                "size_bytes":  f.file.size if f.file else 0,
                "created_at":  f.created_at.isoformat(),
            }
            for f in obj.files.all().order_by("-created_at")
        ]

    class Meta:
        model  = Record
        fields = [
            "id", "title", "abstract", "abstract_file",
            "year_accomplished", "year_completed",
            "classification", "psced", "record_type",
            "classification_name", "record_type_name", "file_count",
            "adviser", "added_by", "is_ip", "ip_type",
            "for_commercialization", "community_extension",
            "requires_ethics_review", "requested_itso", "requested_ierc", "requested_ktto",
            "access_count", "pipeline_status", "is_deleted",
            "created_at", "updated_at",
            "owners", "authors", "reviews", "clearances", "files",
        ]


class RecordWriteSerializer(serializers.ModelSerializer):
    """
    Used for create and update operations.
    `authors` is a flat list of name strings — the serializer handles creating
    and replacing Author rows so callers never touch the Author model directly.
    """
    authors = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=False),
        write_only=True,
        required=False,
        default=list,
        help_text="List of author name strings. On update, replaces all existing authors.",
    )

    class Meta:
        model  = Record
        fields = [
            "id",
            "title", "year_accomplished", "year_completed", "abstract",
            "classification", "psced", "record_type", "adviser",
            "is_ip", "for_commercialization", "community_extension",
            "requires_ethics_review", "requested_itso", "requested_ierc", "requested_ktto",
            "abstract_file",
            "authors",
        ]
        read_only_fields = ["id", "pipeline_status", "added_by"]

    def _sync_authors(self, record, authors_data: list[str]):
        """Replace all Author rows for a record with the provided name list."""
        from .models import Author
        record.authors.all().delete()
        Author.objects.bulk_create(
            [Author(record=record, name=name.strip()) for name in authors_data if name.strip()]
        )

    def create(self, validated_data):
        authors_data = validated_data.pop("authors", [])
        record = super().create(validated_data)
        if authors_data:
            self._sync_authors(record, authors_data)
        return record

    def update(self, instance, validated_data):
        authors_data = validated_data.pop("authors", None)
        record = super().update(instance, validated_data)
        if authors_data is not None:           # only replace when field was explicitly sent
            self._sync_authors(record, authors_data)
        return record


class DownloadRequestSerializer(serializers.ModelSerializer):
    record_title         = serializers.CharField(source="record.title",                    read_only=True)
    requested_by_name    = serializers.SerializerMethodField()
    requested_by_email   = serializers.CharField(source="requested_by.email",              read_only=True)

    class Meta:
        model  = DownloadRequest
        fields = [
            "id", "record", "record_title",
            "requested_by", "requested_by_name", "requested_by_email",
            "status", "reviewed_by", "reviewed_at", "created_at",
        ]
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at"]

    def get_requested_by_name(self, obj):
        if obj.requested_by:
            return obj.requested_by.get_full_name() or obj.requested_by.email
        return None


class DeleteRequestSerializer(serializers.ModelSerializer):
    record_title         = serializers.CharField(source="record.title",                    read_only=True)
    requested_by_name    = serializers.SerializerMethodField()
    requested_by_email   = serializers.CharField(source="requested_by.email",              read_only=True)

    class Meta:
        model  = DeleteRequest
        fields = [
            "id", "record", "record_title",
            "requested_by", "requested_by_name", "requested_by_email",
            "reason", "status", "reviewed_by", "reviewed_at", "created_at",
        ]
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at"]

    def get_requested_by_name(self, obj):
        if obj.requested_by:
            return obj.requested_by.get_full_name() or obj.requested_by.email
        return None


# ---- Reference data serializers -----------------------------------------

class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Classification
        fields = ["id", "name"]


class PSCEDSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PSCEDClassification
        fields = ["id", "name"]


class RecordTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecordType
        fields = ["id", "name"]
