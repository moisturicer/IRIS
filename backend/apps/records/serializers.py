from rest_framework import serializers
from .models import (
    Record, RecordOwner, Author, Publication, Conference,
    Budget, Collaboration, ResearchLink, DownloadRequest, DeleteRequest,
    Classification, PSCEDClassification, RecordType,
)


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Author
        fields = ["id", "name", "role"]


class RecordOwnerSerializer(serializers.ModelSerializer):
    username   = serializers.CharField(source="user.username", read_only=True)
    full_name  = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model  = RecordOwner
        fields = ["id", "user", "username", "full_name", "is_primary"]


class RecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views and DataTable."""
    classification_name = serializers.CharField(source="classification.name", read_only=True)
    record_type_name    = serializers.CharField(source="record_type.name", read_only=True)
    authors             = AuthorSerializer(many=True, read_only=True)

    class Meta:
        model  = Record
        fields = [
            "id", "title", "year_accomplished", "classification_name",
            "record_type_name", "pipeline_status", "is_ip",
            "for_commercialization", "community_extension",
            "access_count", "created_at", "authors",
        ]


class RecordDetailSerializer(serializers.ModelSerializer):
    """Full record detail including all related objects."""
    owners        = RecordOwnerSerializer(many=True, read_only=True)
    authors       = AuthorSerializer(many=True, read_only=True)
    classification = serializers.StringRelatedField()
    psced          = serializers.StringRelatedField()
    record_type    = serializers.StringRelatedField()

    class Meta:
        model  = Record
        fields = "__all__"


class RecordWriteSerializer(serializers.ModelSerializer):
    """Used for create and update operations."""
    # TODO: add nested writable authors, budgets, conferences, collaborations
    class Meta:
        model  = Record
        fields = [
            "title", "year_accomplished", "year_completed", "abstract",
            "classification", "psced", "record_type", "adviser",
            "is_ip", "for_commercialization", "community_extension",
            "abstract_file",
        ]
        read_only_fields = ["pipeline_status", "added_by"]


class DownloadRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DownloadRequest
        fields = "__all__"
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at"]


class DeleteRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DeleteRequest
        fields = "__all__"
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at"]


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
