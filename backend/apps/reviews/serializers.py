from rest_framework import serializers
from core.enums import ReviewDecision

from .models import Review, RecordAuthPin


class ReviewSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True)

    class Meta:
        model  = Review
        fields = ["id", "record", "reviewed_by", "reviewed_by_name", "stage", "status", "comment", "created_at"]
        read_only_fields = ["reviewed_by", "stage", "created_at"]


#: The decisions `ReviewViewSet.submit` implements. Listed rather than read from
#: `ReviewDecision.values`: IR-256 added `NEGATIVE_FINDING` to the enum before
#: any behaviour exists for it, and the view's fallthrough would have recorded
#: one as a decline. A new decision is accepted here only when its endpoint is.
SUBMITTABLE_DECISIONS = (
    ReviewDecision.APPROVED,
    ReviewDecision.DECLINED,
    ReviewDecision.REJECTED,
)


class ReviewWriteSerializer(serializers.Serializer):
    record_id = serializers.IntegerField()
    status    = serializers.ChoiceField(choices=[d.value for d in SUBMITTABLE_DECISIONS])
    comment   = serializers.CharField(required=False, allow_blank=True)


class RecordAuthPinSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecordAuthPin
        fields = ["id", "record", "email", "is_used", "created_at"]
        read_only_fields = ["pin", "is_used"]
