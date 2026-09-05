from rest_framework import serializers
from .models import EmbeddingJob


class EmbeddingJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmbeddingJob
        fields = [
            "id", "record", "status", "celery_task_id",
            "error", "created_at", "completed_at",
        ]
        read_only_fields = fields
