from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    notif_type_name = serializers.CharField(source="notif_type.name", read_only=True)
    record_title    = serializers.CharField(source="record.title", read_only=True, default=None)
    sender_name     = serializers.CharField(source="sender.get_full_name", read_only=True, default=None)
    is_read         = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model  = Notification
        fields = [
            "id", "notif_type", "notif_type_name", "message",
            "record", "record_title", "sender", "sender_name",
            "recipient", "broadcast_to_role", "created_at", "is_read",
        ]
