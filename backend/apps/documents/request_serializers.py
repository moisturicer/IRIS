"""
Document requests on the wire (ADR-022 §5; IR-262, reshaped in IR-263).

Output: one request and its items, the same shape for the list endpoint, the
decision endpoints and the tracker's `document_requests`. The viewer shapes
two things, so both come in through the context (`request_context`): Intake's
student/staff wording, and `can_manage`.

Input: the create, decide and withdraw bodies. Only the *shape* is checked
here; who may act, and whether the request is in a state to act on, are the
domain's (`apps.documents.requests`).

Every refusal leaves as `{"detail": "..."}` -- the one string the interface
shows -- through `first_error`.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import DocumentRequest, DocumentRequestItem


class IsoDateTimeField(serializers.ReadOnlyField):
    """`datetime.isoformat()`, exactly as the hand-built payload wrote it."""

    def to_representation(self, value):
        return value.isoformat() if value else None


class BlankAsNullField(serializers.ReadOnlyField):
    """A blank text column reads as `null`: nothing was said."""

    def to_representation(self, value):
        return value or None


# --- output -------------------------------------------------------------------

class DocumentRequestItemSerializer(serializers.ModelSerializer):
    slot             = serializers.ReadOnlyField(source="slot_id")
    upload           = serializers.ReadOnlyField(source="upload_id")
    state_label      = serializers.CharField(source="get_state_display", read_only=True)
    uploaded_at      = serializers.SerializerMethodField()
    rejection_reason = BlankAsNullField()
    decided_at       = IsoDateTimeField()

    class Meta:
        model  = DocumentRequestItem
        fields = [
            "id", "slot", "label", "state", "state_label", "upload", "uploaded_at",
            "rejection_reason", "decided_at",
        ]
        read_only_fields = fields

    def get_uploaded_at(self, item):
        return item.upload.created_at.isoformat() if item.upload else None


class DocumentRequestSerializer(serializers.ModelSerializer):
    label             = serializers.SerializerMethodField()
    state_label       = serializers.CharField(source="get_state_display", read_only=True)
    requested_by      = serializers.SerializerMethodField()
    created_at        = IsoDateTimeField()
    closed_at         = IsoDateTimeField()
    withdrawal_reason = BlankAsNullField()
    can_manage        = serializers.SerializerMethodField()
    items             = DocumentRequestItemSerializer(many=True, read_only=True)

    class Meta:
        model  = DocumentRequest
        fields = [
            "id", "party", "label", "state", "state_label", "message", "requested_by",
            "created_at", "closed_at", "withdrawal_reason", "can_manage", "items",
        ]
        read_only_fields = fields

    def get_label(self, request):
        from apps.reviews.tracker import party_label

        return party_label(request.party, staff_viewer=self.context["staff_viewer"])

    def get_requested_by(self, request):
        return request.requested_by.get_full_name() if request.requested_by else None

    def get_can_manage(self, request):
        """The viewer may accept, reject or withdraw: they can staff its party."""
        return request.party in self.context["staffable_parties"]


def request_context(record, user) -> dict:
    """What `DocumentRequestSerializer` needs to know about the viewer."""
    from apps.reviews.tracker import is_staff_viewer, staffable_parties

    return {
        "staff_viewer": is_staff_viewer(user),
        "staffable_parties": staffable_parties(record, user),
    }


def serialize_requests(record, user, requests) -> list[dict]:
    return DocumentRequestSerializer(
        requests, many=True, context=request_context(record, user)
    ).data


def serialize_request(request: DocumentRequest, user) -> dict:
    return DocumentRequestSerializer(
        request, context=request_context(request.record, user)
    ).data


# --- input --------------------------------------------------------------------

class DocumentRequestItemInputSerializer(serializers.Serializer):
    """`{"slot": id}` for a picklist slot, or `{"label": text}` for "Other"."""

    slot  = serializers.IntegerField(
        required=False, allow_null=True,
        error_messages={"invalid": "That document is not one this record type can be asked for."},
    )
    label = serializers.CharField(
        required=False, allow_blank=True, max_length=200,
        error_messages={"max_length": "A document name is at most 200 characters."},
    )

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Each item needs a slot or a label.")
        if data.get("slot") == "":
            # A blank slot beside a label is an "Other" item, as it always was.
            data = {k: v for k, v in data.items() if k != "slot"}
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs.get("slot") is None and not attrs.get("label"):
            raise serializers.ValidationError("Each item needs a slot or a label.")
        return attrs


class DocumentRequestCreateSerializer(serializers.Serializer):
    """
    `POST /records/<id>/document-requests/`. The record comes in the context,
    because a slot must be on *its* picklist (§2).
    """

    message = serializers.CharField(
        error_messages={
            "required": "Tell the owner why you need these documents.",
            "blank": "Tell the owner why you need these documents.",
            "null": "Tell the owner why you need these documents.",
        },
    )
    items = DocumentRequestItemInputSerializer(
        many=True, allow_empty=False,
        error_messages={
            "required": "Choose at least one document.",
            "empty": "Choose at least one document.",
            "not_a_list": "Choose at least one document.",
            "null": "Choose at least one document.",
        },
    )

    def validate_items(self, items):
        """Picklist slots to `ItemSpec`s, each slot at most once."""
        from .requests import ItemSpec, picklist

        allowed = {slot.pk: slot for slot in picklist(self.context["record"])}
        specs, seen = [], set()
        for item in items:
            slot_id = item.get("slot")
            if slot_id is None:
                specs.append(ItemSpec(slot=None, label=item["label"]))
                continue
            slot = allowed.get(slot_id)
            if slot is None:
                raise serializers.ValidationError(
                    "That document is not one this record type can be asked for."
                )
            if slot.pk in seen:
                raise serializers.ValidationError(f'"{slot.name}" is listed twice.')
            seen.add(slot.pk)
            specs.append(ItemSpec(slot=slot, label=slot.name))
        return specs


class ItemDecisionSerializer(serializers.Serializer):
    """`PATCH /document-request-items/<id>/` (§3.4)."""

    action = serializers.ChoiceField(
        choices=["accept", "reject"],
        error_messages={"invalid_choice": "The action is accept or reject."},
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["action"] == "reject" and not attrs["reason"]:
            raise serializers.ValidationError(
                "Tell the owner why the upload does not satisfy the request."
            )
        return attrs


class WithdrawSerializer(serializers.Serializer):
    """`PATCH /document-requests/<id>/` (§4). The reason is optional."""

    action = serializers.ChoiceField(
        choices=["withdraw"],
        error_messages={"invalid_choice": "The only action on a request is withdraw."},
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")


def first_error(errors) -> str:
    """The first message in a serializer's errors, however deeply nested."""
    if isinstance(errors, (dict, list)):
        values = errors.values() if isinstance(errors, dict) else errors
        return next((found for found in map(first_error, values) if found), "")
    return str(errors)
