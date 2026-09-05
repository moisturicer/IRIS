from rest_framework import serializers

from .models import Opportunity


class OpportunitySerializer(serializers.ModelSerializer):
    # Derived server-side so every client renders the same countdown. Doing this
    # in the browser would drift with the user's clock and timezone.
    days_left        = serializers.SerializerMethodField()
    is_closed        = serializers.SerializerMethodField()
    type_display     = serializers.CharField(source="get_opportunity_type_display", read_only=True)
    posted_by_name   = serializers.SerializerMethodField()

    class Meta:
        model  = Opportunity
        fields = [
            "id", "opportunity_type", "type_display", "title", "posting_office",
            "audience", "description", "funding_ceiling", "external_url",
            "due_date", "is_featured", "tags", "source",
            "posted_by", "posted_by_name", "created_at", "updated_at",
            "days_left", "is_closed",
        ]
        # posted_by is set from request.user in perform_create, never accepted
        # from the client -- otherwise a poster could attribute a call to
        # somebody else.
        read_only_fields = ["posted_by", "created_at", "updated_at"]

    def get_days_left(self, obj):
        return obj.days_left()

    def get_is_closed(self, obj):
        return obj.is_closed()

    def get_posted_by_name(self, obj):
        if not obj.posted_by:
            return ""
        return obj.posted_by.get_full_name() or obj.posted_by.email

    def validate_tags(self, value):
        if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
            raise serializers.ValidationError("Tags must be a list of strings.")
        return [t.strip() for t in value if t.strip()]
