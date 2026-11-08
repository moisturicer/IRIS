"""
An owner names a paper's Contact person (ADR-051 decision 27, IR-801).

The Contact person is the owner who gets the review emails: decisions,
revision requests, document requests and rejected documents
(`notifications.services` picks the `is_primary` owner when it sends). Every
owner still gets the in-app notice.

Any owner may name any co-owner, on every record type, at any time until the
paper is deleted. RDCO, the Adviser and the offices have no say, which the
view's `IsRecordOwner` gate enforces. The paper's stored AI answer (ADR-054
decision 10, IR-791) is the Contact person's answer *when the draft was
created*, so this act leaves `Record.ai_consent` alone.

Called under the per-record lock `RecordViewSet._paper_under_lock` takes.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from apps.audit import workflow as audit

from .models import Record
from .rdco_acts import owners_payload
from .services import NotAnOwner, set_primary_owner

#: The request body's field: the user id of the owner to name.
OWNER_FIELD = "owner"

NOT_AN_OWNER = "Choose one of this paper's owners."
ACCOUNT_CLOSED = "That owner's account is closed, so they can't be the Contact person."
ALREADY_CONTACT = "That owner is already the Contact person."


def change_contact_person(record: Record, owner_id, *, actor) -> dict:
    """
    Make the owner whose user id is `owner_id` the Contact person of `record`.

    Refuses, with a 400 and nothing written, a missing or malformed id, someone
    who doesn't own this paper, an owner whose account is closed (the emails
    would go nowhere), and the person who already is the Contact person. Both
    the old and the new Contact person are told in-app after commit, and one
    audit event names the paper, both people and `actor`.
    """
    from apps.notifications.services import notify_contact_person_changed

    links = list(record.owners.select_related("user").order_by("pk"))
    target = next((link for link in links if _same_id(link.user_id, owner_id)), None)
    if target is None:
        raise serializers.ValidationError({OWNER_FIELD: [NOT_AN_OWNER]})
    if target.is_primary:
        raise serializers.ValidationError({OWNER_FIELD: [ALREADY_CONTACT]})
    if not target.user.is_active:
        raise serializers.ValidationError({OWNER_FIELD: [ACCOUNT_CLOSED]})
    previous = next((link.user for link in links if link.is_primary), None)

    try:
        set_primary_owner(record, target.user)
    except NotAnOwner:  # Removed between the read and the lock; the lock makes this unreachable today.
        raise serializers.ValidationError({OWNER_FIELD: [NOT_AN_OWNER]})

    audit.contact_person_changed(record, actor, previous=previous, contact=target.user)
    transaction.on_commit(lambda: notify_contact_person_changed(
        record, changed_by=actor, previous=previous, contact=target.user,
    ))
    return {"owners": owners_payload(record)}


def _same_id(user_id: int, given) -> bool:
    """`given` names `user_id`: an int, or a string of digits. Never a bool."""
    if isinstance(given, bool):
        return False
    if isinstance(given, int):
        return given == user_id
    if isinstance(given, str) and given.strip().isdigit():
        return int(given.strip()) == user_id
    return False
