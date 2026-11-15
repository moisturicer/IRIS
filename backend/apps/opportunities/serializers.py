from django.core.validators import URLValidator
from rest_framework import serializers

from django.utils import timezone

from apps.records.models import Classification
from core.enums import CallStatus

from . import capabilities
from core.permissions import is_call_moderator

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
    # ADR-050 decision 8 (IR-762): decided by the server, never by the client.
    status_label     = serializers.CharField(source="get_status_display", read_only=True)
    posted_by_name   = serializers.SerializerMethodField()
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
            "event_state", "event_label", "status", "status_label", "review_reason",
            "reviewed_at",
        ]
        # posted_by is set from request.user in perform_create, never accepted
        # from the client -- otherwise a poster could attribute a call to
        # somebody else.
        read_only_fields = [
            "posted_by", "created_at", "updated_at", "status", "review_reason", "reviewed_at",
        ]
        extra_kwargs = {
            "description": {"required": True, "allow_blank": False},
            "location":    {"required": True, "allow_blank": False},
        }

    # Required on every save, including a PATCH that leaves them out: a Call
    # migrated from a Conference Deadline may lack them, and must carry them
    # by its next save (ADR-050 decision 16).
    REQUIRED_ON_SAVE = ("description", "location", "external_url")

    PAST_DEADLINE = "The paper deadline has passed. Use today's date or a later one."
    NOT_FEATURABLE = "Only a waiting or confirmed Call can be featured."

    def _by_moderator(self):
        request = self.context.get("request")
        return request is not None and is_call_moderator(request.user)

    def validate(self, attrs):
        if self._by_moderator():
            self._check_featured(attrs)
        else:
            # Featured is RDCO's alone, and ignored from anyone else (decision 12).
            attrs.pop("is_featured", None)
            self._check_deadline(attrs)
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

    def _check_featured(self, attrs):
        call_status = self.instance.status if self.instance else CallStatus.CONFIRMED
        if attrs.get("is_featured") and call_status == CallStatus.REJECTED:
            raise serializers.ValidationError({"is_featured": [self.NOT_FEATURABLE]})

    def _check_deadline(self, attrs):
        """
        An Adviser can't save a Call whose paper deadline has passed (ADR-050
        decision 5, as amended 2026-11-15). The deadline checked is the one
        the Call would have after this save, so an edit that leaves a past
        deadline alone is refused too: it would return the Call to RDCO, and
        the daily job deletes a waiting Call past its deadline. RDCO's dates
        stay unchecked.
        """
        due = attrs.get("due_date", getattr(self.instance, "due_date", None))
        if due is not None and due < timezone.localdate():
            raise serializers.ValidationError({"due_date": [self.PAST_DEADLINE]})

    def to_representation(self, obj):
        """
        Every Call carries what this viewer may do with it (IR-530, IR-762):
        capabilities, not a role, so the client never re-derives the rules and
        cannot drift from them. See `capabilities.for_viewer`.
        """
        data = super().to_representation(obj)
        request = self.context.get("request")
        if request is not None:
            data.update(capabilities.for_viewer(obj, request.user))
        return data

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

    def get_posted_by_name(self, obj):
        return obj.poster_name()


class ReasonSerializer(serializers.Serializer):
    """RDCO's reason for rejecting or removing an Adviser's Call (decisions 8 and 11)."""

    reason = serializers.CharField(max_length=2000, trim_whitespace=True)


class DecisionSerializer(serializers.Serializer):
    """
    A confirm names the version RDCO saw: the Call's `updated_at` as served.
    A Call edited since then is refused (409) rather than decided unseen.
    """

    updated_at = serializers.DateTimeField()


class RejectionSerializer(DecisionSerializer, ReasonSerializer):
    """A rejection names the version RDCO saw and gives the reason the Adviser receives."""
