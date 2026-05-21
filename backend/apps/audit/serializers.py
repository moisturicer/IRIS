from rest_framework import serializers
from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    user_name   = serializers.CharField(source="user.get_full_name", read_only=True, default=None)
    record_title = serializers.CharField(source="record.title", read_only=True, default=None)

    class Meta:
        model  = AuditEvent
        fields = ["id", "event_type", "user", "user_name", "record", "record_title", "metadata", "created_at"]
