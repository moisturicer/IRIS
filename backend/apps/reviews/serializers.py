from rest_framework import serializers
from .models import Review, RecordAuthPin


class ReviewSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True)

    class Meta:
        model  = Review
        fields = ["id", "record", "reviewed_by", "reviewed_by_name", "stage", "status", "comment", "created_at"]
        read_only_fields = ["reviewed_by", "stage", "created_at"]


class ReviewWriteSerializer(serializers.Serializer):
    record_id = serializers.IntegerField()
    status    = serializers.ChoiceField(choices=["approved", "declined"])
    comment   = serializers.CharField(required=False, allow_blank=True)


class RecordAuthPinSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecordAuthPin
        fields = ["id", "record", "email", "is_used", "created_at"]
        read_only_fields = ["pin", "is_used"]
