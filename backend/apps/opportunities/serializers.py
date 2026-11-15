from django.core.validators import URLValidator
from rest_framework import serializers

from apps.records.models import Classification
from core.permissions import IsOpportunityPoster

from .models import Opportunity


class OpportunitySerializer(serializers.ModelSerializer):
    # Derived server-side so every client renders the same countdown. Doing this
    # in the browser would drift with the user's clock and timezone.
    days_left        = serializers.SerializerMethodField()
    is_closed        = serializers.SerializerMethodField()
    # ADR-050 decision 6 (IR-761): two independent states, worded here so
    # every client shows the same tag. `event_state` is null when none applies.
    papers_state     = serializers.SerializerMethodField()
    papers_label     = serializers.SerializerMethodField()
    event_state      = serializers.SerializerMethodField()
    event_label      = serializers.SerializerMethodField()
    type_display     = serializers.CharField(source="get_opportunity_type_display", read_only=True)
    posted_by_name   = serializers.SerializerMethodField()
    # A capability, not a role (IR-530): the board shows Edit and Delete from
    # this field, so the client never re-derives the poster rule and cannot
    # drift from it. Decided by the same class that guards update and destroy.
    can_edit         = serializers.SerializerMethodField()
    # At least one Area, always a Classification (ADR-050 amendment 1).
    areas            = serializers.PrimaryKeyRelatedField(
        many=True, allow_empty=False, queryset=Classification.objects.all(),
    )
    area_names       = serializers.SerializerMethodField()
    # The link opens in a reader's browser, so only a web address is accepted:
    # URLField's default also allows ftp:// and ftps://.
    external_url     = serializers.CharField(
        max_length=500, validators=[URLValidator(schemes=["http", "https"])],
    )

    class Meta:
        model  = Opportunity
        fields = [
            "id", "opportunity_type", "type_display", "title", "description",
            "external_url", "due_date", "location", "areas", "area_names",
            "start_date", "end_date", "registration_fee", "is_featured",
            "posted_by", "posted_by_name", "created_at", "updated_at",
            "days_left", "is_closed", "papers_state", "papers_label",
            "event_state", "event_label", "can_edit",
        ]
        # posted_by is set from request.user in perform_create, never accepted
        # from the client -- otherwise a poster could attribute a call to
        # somebody else.
        read_only_fields = ["posted_by", "created_at", "updated_at"]
        extra_kwargs = {
            "description": {"required": True, "allow_blank": False},
            "location":    {"required": True, "allow_blank": False},
        }

    # Required on every save, including a PATCH that leaves them out: a Call
    # migrated from a Conference Deadline may lack them, and must carry them
    # by its next save (ADR-050 decision 16).
    REQUIRED_ON_SAVE = ("description", "location", "external_url")

    def validate(self, attrs):
        if self.instance is None:
            return attrs
        missing = {
            name: ["This field is required."]
            for name in self.REQUIRED_ON_SAVE
            if name not in attrs and not getattr(self.instance, name)
        }
        if "areas" not in attrs and not self.instance.areas.exists():
            missing["areas"] = ["This field is required."]
        if missing:
            raise serializers.ValidationError(missing)
        return attrs

    def get_days_left(self, obj):
        return obj.days_left()

    def get_is_closed(self, obj):
        return obj.is_closed()

    def get_papers_state(self, obj):
        return obj.papers_state()

    def get_papers_label(self, obj):
        return obj.papers_label()

    def get_event_state(self, obj):
        return obj.event_state()

    def get_event_label(self, obj):
        return obj.event_label()

    def get_area_names(self, obj):
        return sorted(area.name for area in obj.areas.all())

    def get_can_edit(self, obj):
        request = self.context.get("request")
        if request is None:
            return False
        view = self.context.get("view")
        permission = IsOpportunityPoster()
        return (
            permission.has_permission(request, view)
            and permission.has_object_permission(request, view, obj)
        )

    def get_posted_by_name(self, obj):
        return obj.poster_name()
