"""
Document requests: a reviewer asks the owner for documents (ADR-022, IR-262).

ADR-022 §3 and §4. Creating a request, fulfilling it, accepting or rejecting
an upload and withdrawing it (IR-263) are the writes, and **none of them
touches the record's workflow**: no `pipeline_status` change, no clearance
reset, no assignment closed. The record's `awaiting_document` state is derived
from open requests by `apps.reviews.tracker` and never stored.

Who does what (§Amendment 2): the requesting party creates, decides and
withdraws; only the Record's owners fulfil. A decision closing open requests
(§3) is IR-270's.

The wire shape is `request_serializers`; this module builds no payload.
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


def requesting_party(record, user, party=None) -> str:
    """
    The party `user` asks as: `party`, or the only one they hold.

    ADR-022 §Security: the user must hold the record -- an active assignment
    for a party they can staff (`tracker.requestable_parties`). Asked before
    the body is validated, so someone who may not ask is told that first.
    """
    from apps.reviews.tracker import requestable_parties

    parties = requestable_parties(record, user)
    if party in (None, ""):
        if len(parties) != 1:
            if not parties:
                raise NotAHolder("You do not hold this record.")
            raise DocumentRequestError("Say which party you are asking as.")
        return parties[0]
    if party not in parties:
        raise NotAHolder("You do not hold this record as that party.")
    return party


def create_request(record, user, *, party, message, specs: list[ItemSpec]) -> DocumentRequest:
    """Open a request as `party`, which `requesting_party` has already vetted."""
    from apps.reviews.models import RecordAssignment
    from core.enums import AssignmentState

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


def may_read_requests(record, user) -> bool:
    """
    May `user` read `record`'s document requests? (IR-349, ADR-022 §Amendment 5)

    Document-request data is internal workflow data, so reading the Record --
    published, or through `visible_to()` for an office -- is not enough. Access
    is by **participation, never by role**: the user owns the Record, asked for
    documents on it, or can staff a party that holds or held an assignment on
    it, reviewed or signed a clearance on it, or asked for documents on it.

    The one rule for every route that serves the data: the list endpoint and
    the tracker's `document_requests` and per-party `awaiting_document`.
    """
    from apps.reviews.tracker import participating_parties, staffable_parties

    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if record.owners.filter(user=user).exists():
        return True
    if DocumentRequest.objects.filter(record=record, requested_by=user).exists():
        return True

    staffable = staffable_parties(record, user)
    if not staffable:
        return False
    requesting = set(
        DocumentRequest.objects.filter(record=record).values_list("party", flat=True)
    )
    return bool(staffable & (participating_parties(record) | requesting))


def may_fulfil(record, user) -> bool:
    """
    Only the Record's owners answer a request (ADR-022 §Amendment 2, IR-263).
    §Amendment 2's "authorised submitter" is a `RecordOwner`: co-authors are
    added as owners, and IRIS has no other kind of submitter.

    Staff pass `authorize_record_documents` on every Record, so without this
    the office that asked could answer its own request by uploading the file.
    """
    return bool(
        user is not None and getattr(user, "is_authenticated", False)
        and record.owners.filter(user=user).exists()
    )


def is_requester(request: DocumentRequest, user) -> bool:
    """`user` can staff the party that asked. The party counts, not the person."""
    from apps.reviews.tracker import staffable_parties

    return request.party in staffable_parties(request.record, user)


def request_on_visible_record(request_id, user) -> Optional[DocumentRequest]:
    """
    The request, or None when there is none or `user` cannot see its Record.

    Only those two read as a missing id (ADR-022 §Amendment 4, 404). Seeing the
    Record but not its request data is a separate refusal, a 403, and the
    caller asks `may_read_requests` for it: a 404 never hides request
    authorization on a visible Record (settled 2026-09-24).
    """
    from apps.records.models import Record

    try:
        request = DocumentRequest.objects.select_related("record").get(pk=int(request_id))
    except (DocumentRequest.DoesNotExist, TypeError, ValueError):
        return None
    if not Record.objects.visible_to(user).filter(pk=request.record_id).exists():
        return None
    return request


def _lock_decidable(item: DocumentRequestItem) -> tuple[DocumentRequestItem, DocumentRequest]:
    """
    Lock the item, then its request -- the order the upload path locks them,
    so a decision and an upload cannot interleave -- and confirm the item is
    an upload awaiting the requesting party's verdict. Call in a transaction.
    """
    item = DocumentRequestItem.objects.select_for_update().get(pk=item.pk)
    request = DocumentRequest.objects.select_for_update().get(pk=item.request_id)
    if request.state == DocumentRequestState.WITHDRAWN:
        raise DocumentRequestError("That request was withdrawn.")
    if item.state != DocumentRequestItemState.UPLOADED:
        raise DocumentRequestError("Only an uploaded document can be accepted or rejected.")
    return item, request


def accept_item(item: DocumentRequestItem) -> DocumentRequest:
    """
    The upload satisfies the request (ADR-022 §3.4). A request whose items
    were all uploaded is already fulfilled, so it stays closed. The caller has
    checked `is_requester`.
    """
    with transaction.atomic():
        item, request = _lock_decidable(item)
        item.state = DocumentRequestItemState.ACCEPTED
        item.decided_at = timezone.now()
        item.save(update_fields=["state", "decided_at"])
    return request


def reject_item(item: DocumentRequestItem, user, *, reason: str) -> DocumentRequest:
    """
    The upload does not satisfy the request (ADR-022 §3.4). The item goes
    back to `missing` with `reason` and forgets the upload -- the file version
    itself stays on the Record -- the request reopens, and the owners are told
    once the transaction commits. The caller has checked `is_requester`.
    """
    with transaction.atomic():
        item, request = _lock_decidable(item)
        item.state = DocumentRequestItemState.MISSING
        item.upload = None
        item.rejection_reason = reason
        item.decided_at = timezone.now()
        item.save(update_fields=["state", "upload", "rejection_reason", "decided_at"])
        if request.state != DocumentRequestState.OPEN:
            request.state = DocumentRequestState.OPEN
            request.closed_at = None
            request.save(update_fields=["state", "closed_at"])

        from apps.notifications.services import notify_document_rejected

        transaction.on_commit(
            lambda: notify_document_rejected(request, item, rejected_by=user)
        )
    return request


def withdraw_request(request: DocumentRequest) -> DocumentRequest:
    """
    The requesting party no longer needs it (ADR-022 §4). Only an open
    request: a fulfilled one is already closed, and its uploads are decided
    item by item. It stays in the history; the owner's panel drops it.

    No reason is recorded: IR-263 adds none, and IR-270 defines any a
    decision needs when it closes requests.
    """
    with transaction.atomic():
        request = DocumentRequest.objects.select_for_update().get(pk=request.pk)
        if request.state != DocumentRequestState.OPEN:
            raise DocumentRequestError("Only an open request can be withdrawn.")
        request.state = DocumentRequestState.WITHDRAWN
        request.closed_at = timezone.now()
        request.save(update_fields=["state", "closed_at"])
    return request


def requests_for(record):
    """Every request on `record`, oldest first, ready for `payload`."""
    return (
        DocumentRequest.objects.filter(record=record)
        .select_related("requested_by")
        .prefetch_related("items__upload")
        .order_by("created_at", "pk")
    )
