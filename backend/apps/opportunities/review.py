"""
RDCO's review of an Adviser's Call (ADR-050 decisions 8-11, amended
2026-11-15; IR-762).

Each act locks the Call's row and checks its status inside the same
transaction, so two RDCO accounts deciding the same request at once cannot
both succeed: the second sees a Call that is no longer pending and is refused.
Notices are sent after the change is committed, so a rolled-back act never
tells anyone it happened. Confirm, reject and remove write their audit
event (IR-763) inside the same transaction, so a refused or rolled-back act
records nothing; an edit's event, the resubmission included, is the view's.
"""
from django.db import transaction
from django.utils import timezone

from apps.notifications import services as notify
from apps.notifications.settling import settle_call
from core.enums import CallStatus

from . import audit
from .models import Opportunity


class NotWaiting(Exception):
    """The Call has already been decided, or its paper deadline has passed."""


class ChangedSinceSeen(Exception):
    """The Adviser edited the Call after RDCO opened it: RDCO hasn't seen what it would decide."""


def _locked(call_id):
    """The Call, locked for this transaction. Gone since it was read: DoesNotExist, a 404."""
    return Opportunity.objects.select_for_update().get(pk=call_id)


def _locked_waiting(call_id, seen):
    """
    The Call RDCO is deciding, locked, provided it still waits and is the
    version RDCO saw (`seen`, its `updated_at` then). Without the second check
    an Adviser's edit made while RDCO read the request would be confirmed
    unseen.
    """
    call = _locked(call_id)
    if not call.is_waiting():
        raise NotWaiting
    if call.updated_at != seen:
        raise ChangedSinceSeen
    return call


def changes_anything(call, data) -> bool:
    """Would saving `data` (validated serializer fields) change `call`?"""
    for name, value in data.items():
        if name == "areas":
            if {area.pk for area in value} != {area.pk for area in call.areas.all()}:
                return True
        elif getattr(call, name) != value:
            return True
    return False


def confirm(call_id, *, by, seen):
    with transaction.atomic():
        call = _locked_waiting(call_id, seen)
        call.status = CallStatus.CONFIRMED
        call.review_reason = ""
        call.reviewed_at = timezone.now()
        call.save(update_fields=["status", "review_reason", "reviewed_at", "updated_at"])
        audit.confirmed(call, by=by)
        transaction.on_commit(lambda: notify.notify_call_confirmed(call, confirmed_by=by))
    return call


def reject(call_id, *, by, seen, reason):
    with transaction.atomic():
        call = _locked_waiting(call_id, seen)
        call.status = CallStatus.REJECTED
        call.review_reason = reason
        call.reviewed_at = timezone.now()
        call.save(update_fields=["status", "review_reason", "reviewed_at", "updated_at"])
        audit.rejected(call, by=by, reason=reason)
        transaction.on_commit(lambda: notify.notify_call_rejected(call, rejected_by=by, reason=reason))
    return call


def remove(call_id, *, by, reason):
    """
    RDCO deletes a Call with a reason (decision 11). The poster receives it
    when an Adviser posted the Call; a colleague's or a departed poster's
    Call needs no notice. The Python object outlives the row, so the notice
    can still name the Call after it is gone.
    """
    with transaction.atomic():
        call = _locked(call_id)
        tell = call.posted_by_adviser()
        before = audit.snapshot(call)
        call.delete()
        audit.removed(before, by=by, reason=reason)
        if tell:
            transaction.on_commit(lambda: notify.notify_call_removed(call, removed_by=by, reason=reason))


def submitted(call):
    """A new Adviser's Call is waiting: tell RDCO once it is committed."""
    transaction.on_commit(lambda: notify.notify_call_requested(call))


def returned_for_review(call):
    """
    An Adviser's edit sent a confirmed or rejected Call back to RDCO
    (decision 10). RDCO's notices about its earlier request are settled first,
    while the row still says how that one ended; the new request then sends a
    notice of its own (ADR-069 decision 5). The caller saves the Call in the
    same transaction, holding its row lock, so the notice goes out only once the
    edit is committed and names the Call as edited.
    """
    settle_call(call)
    call.status = CallStatus.PENDING
    call.review_reason = ""
    transaction.on_commit(lambda: notify.notify_call_requested(call, resubmitted=True))
