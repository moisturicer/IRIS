"""
What a viewer may do with one Call (IR-762, ADR-050 decisions 8-12).

Sent with every Call so the screens (IR-765) offer exactly the acts the
server will accept and compare no role names. Each answer restates the rule
the matching endpoint enforces; `test_call_review.CapabilityTests` pins them
together.
"""
from django.utils import timezone

from core.enums import CallStatus
from core.permissions import OPPORTUNITY_POSTER_ROLES, get_role_name, is_call_moderator


def for_viewer(call, user, today=None) -> dict:
    today = today or timezone.localdate()
    moderator = is_call_moderator(user)
    poster = get_role_name(user) in OPPORTUNITY_POSTER_ROLES
    own = call.posted_by_id == user.pk
    # Offered even once an Adviser's deadline has passed: moving it forward is
    # accepted, and only a save that keeps a past deadline is refused.
    can_edit = poster and (moderator or own)
    deciding = moderator and call.is_waiting(today)
    return {
        "can_edit": can_edit,
        # RDCO deletes an Adviser's Call only with a reason, through `remove`.
        "can_delete": poster and (own or (moderator and not call.posted_by_adviser())),
        "can_remove": moderator and call.posted_by_adviser(),
        "can_confirm": deciding,
        "can_reject": deciding,
        "can_feature": moderator and call.status in (CallStatus.PENDING, CallStatus.CONFIRMED),
        # The form warns an Adviser before an edit sends the Call back to RDCO.
        "edit_returns_to_pending": can_edit and not moderator and call.status != CallStatus.PENDING,
    }
