from rest_framework import serializers
from .models import Notification, TaskKind

# Where a notice that carries no Record opens (IR-765). A Call's notices name
# no Record, so without this they had nowhere to go. Decided here, once, so a
# screen never infers a destination from a type's name or the viewer's role.
CALL_REQUESTS_PAGE = "/rdco/call-requests"
TARGET_BY_TYPE = {
    "Call Confirmed":      "/opportunities",
    "Call Rejected":       "/opportunities/mine",
    "Call Removed":        "/opportunities/mine",
    "Call Request Lapsed": "/opportunities/mine",
}


class NotificationSerializer(serializers.ModelSerializer):
    notif_type_name = serializers.CharField(source="notif_type.name", read_only=True)
    record_title    = serializers.CharField(source="record.title", read_only=True, default=None)
    sender_name     = serializers.CharField(source="sender.get_full_name", read_only=True, default=None)
    is_read         = serializers.BooleanField(read_only=True, default=False)
    # The page to open, for a notice that names no Record; null otherwise.
    target          = serializers.SerializerMethodField()

    class Meta:
        model  = Notification
        fields = [
            "id", "notif_type", "notif_type_name", "message",
            "record", "record_title", "sender", "sender_name",
            "recipient", "broadcast_to_role", "created_at", "is_read",
            "resolved_at", "resolved_label", "target",
        ]

    def get_target(self, obj):
        if obj.task_kind == TaskKind.CALL_REQUEST:
            return CALL_REQUESTS_PAGE
        return TARGET_BY_TYPE.get(obj.notif_type.name if obj.notif_type_id else "")
