"""
Audit events for every act on a Call (ADR-050 decision 15, IR-763).

Called inside the act's own transaction, after the row lock, so a refused or
rolled-back act leaves no event. `create_audit_event` never raises: a failed
insert is rolled back to its savepoint and logged at ERROR, and the act still
commits without its event (the IR-144 design). The metadata keys are fixed
here and documented in `docs/evaluation/AUDIT_EXPORT.md`: change one, change
both.

A Call is not a paper, so no event has a `record`. A deletion's snapshot is
the only trace of the Call left once its row is gone.
"""
from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event

#: Every field of a Call, in a snapshot. A test checks this against the
#: model, so a field added later can't silently drop out of the copy.
COPIED_FIELDS = (
    "id", "opportunity_type", "title", "description", "external_url", "due_date",
    "location", "areas", "start_date", "end_date", "registration_fee", "is_featured",
    "status", "review_reason", "reviewed_at", "posted_by", "created_at", "updated_at",
)


def _json(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def snapshot(call) -> dict:
    """Every field of the Call, as JSON: Areas as ids and names, the poster as an id."""
    fields = {
        name: _json(getattr(call, name))
        for name in COPIED_FIELDS if name not in ("areas", "posted_by")
    }
    fields["areas"] = sorted(
        ({"id": area.pk, "name": area.name} for area in call.areas.all()),
        key=lambda area: area["id"],
    )
    fields["posted_by"] = call.posted_by_id
    return fields


def _identity(call) -> dict:
    return {"call_id": call.pk, "title": call.title}


def posted(call, *, by) -> None:
    create_audit_event(AuditEvent.CALL_POSTED, by, metadata={"call": snapshot(call)})


def edited(before: dict, call, *, by) -> None:
    """
    One event for one saved edit, holding each changed field's old and new
    value. `updated_at` changes on every save, so it is never reported, and a
    save that changed nothing else writes nothing.
    """
    after = snapshot(call)
    changes = {
        name: {"old": before[name], "new": after[name]}
        for name in COPIED_FIELDS
        if name != "updated_at" and before[name] != after[name]
    }
    if changes:
        create_audit_event(AuditEvent.CALL_EDITED, by, metadata={**_identity(call), "changes": changes})


def deleted(before: dict, *, by) -> None:
    """A person deleted the Call; `before` is its snapshot, taken while the row existed."""
    create_audit_event(AuditEvent.CALL_DELETED, by, metadata={"reason": None, "call": before})


def confirmed(call, *, by) -> None:
    create_audit_event(AuditEvent.CALL_CONFIRMED, by, metadata=_identity(call))


def rejected(call, *, by, reason) -> None:
    create_audit_event(AuditEvent.CALL_REJECTED, by, metadata={**_identity(call), "reason": reason})


def removed(before: dict, *, by, reason) -> None:
    create_audit_event(AuditEvent.CALL_REMOVED, by, metadata={"reason": reason, "call": before})


def lapsed(before: dict) -> None:
    """The daily job deleted a request whose paper deadline passed. No actor."""
    create_audit_event(AuditEvent.CALL_LAPSED, None, metadata={"call": before})
