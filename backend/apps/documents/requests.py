"""
Document requests: a reviewer asks the owner for documents (ADR-022, IR-262).

ADR-022 §3. Creating a request and fulfilling it are the only two writes, and
**neither touches the record's workflow**: no `pipeline_status` change, no
clearance reset, no assignment closed. The record's `awaiting_document` state is
derived from open requests by `apps.reviews.tracker` and never stored.

Accepting, rejecting and withdrawing (§3.4, §4) are IR-263's. A decision closing
open requests (§3) is IR-270's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from core.enums import DocumentRequestItemState, DocumentRequestState

from .models import DocumentRequest, DocumentRequestItem, UploadSlot


class DocumentRequestError(Exception):
    """A request the caller may make, but not in this shape. Maps to 400."""


class NotAHolder(Exception):
    """The caller does not hold the record as any party it could ask for. 403."""


@dataclass(frozen=True)
class ItemSpec:
    slot: Optional[UploadSlot]
    label: str


def picklist(record):
    """The slots a reviewer chooses from: the record type's, never an ad-hoc one (§2)."""
    return UploadSlot.objects.filter(
        record_type_id=record.record_type_id, record__isnull=True
    ).order_by("pk")


def parse_items(record, raw_items) -> list[ItemSpec]:
    """
    `[{"slot": id} | {"label": text}, ...]` to item specs.

    A slot must be on this record's picklist. A label alone is an "Other" item.
    """
    if not isinstance(raw_items, list) or not raw_items:
        raise DocumentRequestError("Choose at least one document.")

    allowed = {slot.pk: slot for slot in picklist(record)}
    specs: list[ItemSpec] = []
    seen_slots: set[int] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise DocumentRequestError("Each item needs a slot or a label.")
        slot_id = raw.get("slot")
        label = str(raw.get("label") or "").strip()
        if slot_id not in (None, ""):
            try:
                slot = allowed[int(slot_id)]
            except (KeyError, TypeError, ValueError):
                raise DocumentRequestError(
                    "That document is not one this record type can be asked for."
                )
            if slot.pk in seen_slots:
                raise DocumentRequestError(f'"{slot.name}" is listed twice.')
            seen_slots.add(slot.pk)
            specs.append(ItemSpec(slot=slot, label=slot.name))
        elif label:
            if len(label) > 200:
                raise DocumentRequestError("A document name is at most 200 characters.")
            specs.append(ItemSpec(slot=None, label=label))
        else:
            raise DocumentRequestError("Each item needs a slot or a label.")
    return specs


def create_request(record, user, *, message, raw_items, party=None) -> DocumentRequest:
    """
    Open a request as `party` (inferred when the user holds exactly one).

    ADR-022 §Security: the user must hold the record -- an active assignment
    for a party they can staff (`tracker.requestable_parties`).
    """
    from apps.reviews.models import RecordAssignment
    from apps.reviews.tracker import requestable_parties
    from core.enums import AssignmentState

    parties = requestable_parties(record, user)
    if party in (None, ""):
        if len(parties) != 1:
            if not parties:
                raise NotAHolder("You do not hold this record.")
            raise DocumentRequestError("Say which party you are asking as.")
        party = parties[0]
    elif party not in parties:
        raise NotAHolder("You do not hold this record as that party.")

    message = str(message or "").strip()
    if not message:
        raise DocumentRequestError("Tell the owner why you need these documents.")
    specs = parse_items(record, raw_items)

    with transaction.atomic():
        request = DocumentRequest.objects.create(
            record=record,
            assignment=RecordAssignment.objects.filter(
                record=record, party=party, state=AssignmentState.ACTIVE
            ).first(),
            party=party,
            requested_by=user,
            message=message,
        )
        DocumentRequestItem.objects.bulk_create(
            DocumentRequestItem(request=request, slot=s.slot, label=s.label, sort_order=i)
            for i, s in enumerate(specs)
        )
    return request


def slot_accepts_uploads_for(slot: UploadSlot, record) -> bool:
    """An ad-hoc slot belongs to one record; any other slot to none in particular."""
    return slot.record_id is None or slot.record_id == record.pk


def _adhoc_slot(record, label: str) -> UploadSlot:
    # First-or-create rather than get_or_create: nothing makes (record, name)
    # unique, and a duplicate left by a race must not turn every later upload
    # into MultipleObjectsReturned.
    existing = UploadSlot.objects.filter(record=record, name=label).order_by("pk").first()
    return existing or UploadSlot.objects.create(
        record=record, name=label, record_type_id=record.record_type_id, is_required=False,
    )


def resolve_item_for_upload(record, item_id, slot_id=None) -> tuple[DocumentRequestItem, UploadSlot]:
    """
    The item an upload answers, and the slot the file belongs in.

    **Call inside a transaction.** The item and its request are locked, so two
    uploads racing for one item cannot both claim it, and a request closed in
    between is seen closed. The slot comes from the item: its picklist slot, or
    for an "Other" item a slot of this record's own (ADR-022 §3.2). A `slot`
    sent as well must agree with it.

    An item on another record reads exactly like a missing one, so the
    refusal never confirms that someone else's request exists (IR-153).
    """
    try:
        item = (
            DocumentRequestItem.objects.select_for_update(of=("self",))
            .select_related("slot")
            .get(pk=int(item_id), request__record=record)
        )
    except (DocumentRequestItem.DoesNotExist, TypeError, ValueError):
        raise DocumentRequestError("That requested document does not exist.")
    request = DocumentRequest.objects.select_for_update().get(pk=item.request_id)
    if request.state != DocumentRequestState.OPEN:
        raise DocumentRequestError("That request is closed.")
    if item.state != DocumentRequestItemState.MISSING:
        raise DocumentRequestError("That document has already been uploaded.")

    slot = item.slot or _adhoc_slot(record, item.label)
    if slot_id not in (None, "") and str(slot_id) != str(slot.pk):
        raise DocumentRequestError("That slot is not the one this document was requested in.")
    item.request = request
    return item, slot


def fulfil_item(item: DocumentRequestItem, upload, *, uploaded_by) -> DocumentRequest:
    """
    Mark `item` uploaded. When it was the last one missing, the request is
    fulfilled, and the requesting party is told once the transaction commits
    (ADR-022 §3.3). Call inside the transaction `resolve_item_for_upload` ran in.
    """
    request = item.request
    item.upload = upload
    item.state = DocumentRequestItemState.UPLOADED
    item.save(update_fields=["upload", "state"])
    if not request.items.filter(state=DocumentRequestItemState.MISSING).exists():
        request.state = DocumentRequestState.FULFILLED
        request.closed_at = timezone.now()
        request.save(update_fields=["state", "closed_at"])

        from apps.notifications.services import notify_document_request_fulfilled

        transaction.on_commit(
            lambda: notify_document_request_fulfilled(request, uploaded_by=uploaded_by)
        )
    return request


def payload(request: DocumentRequest, *, staff_viewer: bool) -> dict:
    """One request as the API and the tracker state it."""
    from apps.reviews.tracker import party_label

    return {
        "id": request.pk,
        "party": request.party,
        "label": party_label(request.party, staff_viewer=staff_viewer),
        "state": request.state,
        "state_label": request.get_state_display(),
        "message": request.message,
        "requested_by": request.requested_by.get_full_name() if request.requested_by else None,
        "created_at": request.created_at.isoformat(),
        "closed_at": request.closed_at.isoformat() if request.closed_at else None,
        "items": [
            {
                "id": item.pk,
                "slot": item.slot_id,
                "label": item.label,
                "state": item.state,
                "state_label": item.get_state_display(),
                "upload": item.upload_id,
                "uploaded_at": item.upload.created_at.isoformat() if item.upload else None,
            }
            for item in request.items.all()
        ],
    }


def requests_for(record):
    """Every request on `record`, oldest first, ready for `payload`."""
    return (
        DocumentRequest.objects.filter(record=record)
        .select_related("requested_by")
        .prefetch_related("items__upload")
        .order_by("created_at", "pk")
    )
