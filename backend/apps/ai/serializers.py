"""Wire shapes for the AI app's ORM-backed resources.

The retrieval responses are not here — they are built from domain values in
`apps/ai/presentation.py`, which has no model behind it. This module is for
the things that *are* rows.
"""

from rest_framework import serializers

from apps.ai import public as public_protocol
from apps.ai.conversations import turns_for_reader
from apps.records.models import Record

from .models import Conversation, EmbeddingJob


class EmbeddingJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmbeddingJob
        fields = [
            "id", "record", "status", "celery_task_id",
            "error", "created_at", "completed_at",
        ]
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    """One conversation, without its Turns — the shape a sidebar lists.

    ``record``'s queryset is narrowed to what the caller may read, so naming
    a hidden draft is refused exactly as a missing record is.
    """

    record = serializers.PrimaryKeyRelatedField(
        queryset=Record.objects.none(), required=False, allow_null=True
    )
    record_title = serializers.CharField(source="record.title", read_only=True,
                                         default=None)
    # Annotated by `owned_by`, not walked per row.
    turn_count = serializers.IntegerField(read_only=True)
    reuse_default = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = Conversation
        fields = [
            "id", "title", "record", "record_title", "turn_count",
            "created_at", "updated_at",
            "reuse_default",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            self.fields["record"].queryset = Record.objects.visible_to(request.user)

    def validate(self, attrs):
        if attrs.get("reuse_default") and not attrs.get("record"):
            raise serializers.ValidationError({"record": "A default Conversation requires a readable Record."})
        return attrs


class ConversationDetailSerializer(ConversationSerializer):
    """The same conversation with its transcript.

    `turns_for_reader` re-checks every stored citation against the reader's
    visibility now rather than when it was written (ADR-019).
    """

    turns = serializers.SerializerMethodField()
    #: The latest queued run while no Turn shows for it (IR-548), so a reader
    #: opening the Conversation can follow it again or retry it.
    latest_run = serializers.SerializerMethodField()

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ["turns", "latest_run"]

    def get_turns(self, conversation):
        request = self.context["request"]
        return turns_for_reader(conversation, request.user, public=public_protocol.requested(request))

    def get_latest_run(self, conversation):
        from apps.ai.durable import latest_run_for_reader

        run = latest_run_for_reader(conversation)
        if public_protocol.requested(self.context["request"]):
            return public_protocol.project_latest_run(run)
        return run

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only the title is editable: re-scoping would change which Record's
        # deletion takes the transcript with it.
        self.fields["record"].read_only = True
        self.fields["record"].queryset = None
        self.fields["record"].required = False
