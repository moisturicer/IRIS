from rest_framework import serializers
from .models import EmbeddingJob


class EmbeddingJobSerializer(serializers.ModelSerializer):
    record_title = serializers.CharField(source="record.title", read_only=True)

    class Meta:
        model  = EmbeddingJob
        fields = ["id", "record", "record_title", "status", "celery_task_id", "error", "created_at", "completed_at"]


class SemanticSearchResultSerializer(serializers.Serializer):
    answer  = serializers.CharField()
    sources = serializers.ListField()
