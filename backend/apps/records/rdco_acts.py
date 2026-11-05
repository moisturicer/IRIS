"""
RDCO's three acts on a paper in review (ADR-051 decision 10, IR-797).

An account deletion waits until nobody is relying on the person (IR-785), and
three things that block it could not be cleared before this:

- **Replace the Adviser.** Nobody could. The Adviser party has no coordinator
  who could withdraw a seat and seat someone else, as an office has.
- **Add an owner.** `owner_emails` works on a draft only.
- **Withdraw the paper.** Only its owner could, by deleting it.

Each works on any paper in review, deletion or not, and is RDCO's alone. This
module holds **what each act does**; *who may ask* is `IsRDCO`, checked by the
endpoint before the paper is looked up, and `record_capabilities` offers each
act from the same predicates used here.

**Every act runs under the per-record lock** every workflow act takes: the
endpoint takes it (`RecordViewSet._paper_under_lock`) and the act re-reads what
it changes after that, so a Decision, a routing act or an owner's delete on the
same paper runs before or after it, never alongside.

**Each act is one audit event** (`audit.workflow`), written inside the act's
transaction, and its notices go after commit and never raise.

A refusal is a `ValidationError` naming the field it is about, so a 400 says
what to change. Nothing here says whether an account exists beyond the
"existing active, verified account" rule itself.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.utils import timezone
from rest_framework import serializers

from apps.audit import workflow as audit
from core.enums import (
    OPEN_SEAT_STATES,
    AssignmentState,
    Party,
    PipelineStatus,
    RoleName,
    SeatSource,
    SeatState,
)
from core.permissions import ROLE_RDCO, get_role_name

from .models import Record, RecordOwner
from .services import soft_delete_record

#: A reason is read in a notification and an email, so it is bounded.
MAX_REASON_LENGTH = 1000

NOT_IN_REVIEW = "This paper is not in review."
NO_ADVISER_REVIEW = "No Adviser review is open on this paper."
NOT_AN_ADVISER = "Choose an active account that holds the Adviser role."
ALREADY_THE_ADVISER = "That person is already this paper's Adviser."
ADVISER_OWNS = "A paper's Adviser cannot also be one of its owners."
NOT_A_MEMBER = "Use an existing, active, verified account."
ALREADY_AN_OWNER = "That person already owns this paper."
REASON_REQUIRED = "Give a reason for withdrawing the paper."
REASON_TOO_LONG = f"Keep the reason to {MAX_REASON_LENGTH} characters."


def is_rdco(user) -> bool:
    """The act's role gate: RDCO, and no other role (ADR-051 decision 10)."""
    return bool(user and getattr(user, "is_authenticated", False)) and get_role_name(user) == ROLE_RDCO


def adviser_review(record):
    """The paper's active Adviser assignment, or None: what replacing the Adviser hands over."""
    from apps.reviews.models import RecordAssignment

    return RecordAssignment.objects.filter(
        record=record, party=Party.ADVISER, state=AssignmentState.ACTIVE,
    ).first()


def _require_in_review(record) -> None:
    if record.pipeline_status != PipelineStatus.IN_REVIEW:
        raise serializers.ValidationError({"detail": NOT_IN_REVIEW})


def _text(value, field: str, *, required: bool, message: str = "") -> str:
    if value is None or value == "":
        text = ""
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise serializers.ValidationError({field: "Give this as text."})
    if required and not text:
        raise serializers.ValidationError({field: message})
    if len(text) > MAX_REASON_LENGTH:
        raise serializers.ValidationError({field: REASON_TOO_LONG})
    return text


def _name(user) -> str:
    return user.get_full_name() or user.email


# --- replace the Adviser --------------------------------------------------------------

def replace_adviser(record: Record, adviser_id, *, actor, reason="") -> dict:
    """
    Name another Adviser on a paper whose Adviser review is open.

    The old Adviser's open seat is withdrawn and the new one is seated on the
    same assignment, so the review's clock and everything filed against it
    carry on. The new seat records the one it replaced and RDCO's reason
    (the same fields a coordinator's reassignment uses, IR-623). The new
    Adviser starts unopened, as an entry seat does.

    A paper whose Adviser has already finished or been cut off has no Adviser
    review to hand over; that is refused, not forced.
    """
    from apps.accounts.models import User
    from apps.notifications.services import notify_adviser_replaced
    from apps.reviews.models import RecordAssignment, ReviewerSeat

    _require_in_review(record)
    reason = _text(reason, "reason", required=False)
    assignment = (
        RecordAssignment.objects.select_for_update()
        .filter(record=record, party=Party.ADVISER, state=AssignmentState.ACTIVE).first()
    )
    if assignment is None:
        raise serializers.ValidationError({"detail": NO_ADVISER_REVIEW})

    if type(adviser_id) is not int:
        raise serializers.ValidationError({"adviser": NOT_AN_ADVISER})
    adviser = User.objects.filter(
        pk=adviser_id, is_active=True, role__name=RoleName.ADVISER,
    ).first()
    if adviser is None:
        raise serializers.ValidationError({"adviser": NOT_AN_ADVISER})
    if adviser.pk == record.adviser_id:
        raise serializers.ValidationError({"adviser": ALREADY_THE_ADVISER})
    if record.owners.filter(user=adviser).exists():
        # IR-260: the same rule `submit/` and the draft's owners hold.
        raise serializers.ValidationError({"adviser": ADVISER_OWNS})

    previous = record.adviser
    open_seats = list(
        assignment.seats.select_for_update().filter(state__in=OPEN_SEAT_STATES).order_by("pk")
    )
    previous_seat = open_seats[0] if open_seats else None
    for seat in open_seats:
        seat.state = SeatState.WITHDRAWN
        seat.save(update_fields=["state"])

    try:
        with transaction.atomic():
            seat = ReviewerSeat.objects.create(
                assignment=assignment, reviewer=adviser, source=SeatSource.ASSIGNED,
                assigned_by=actor, assigned_at=timezone.now(),
                reassigned_from=previous_seat, reason=reason,
            )
    except IntegrityError:
        # The partial unique constraint, reached by a request the lock did not cover.
        raise serializers.ValidationError({"adviser": ALREADY_THE_ADVISER})

    record.adviser = adviser
    record.save(update_fields=["adviser", "updated_at"])

    audit.adviser_replaced(
        record, actor, previous_adviser=previous, adviser=adviser,
        assignment=assignment, previous_seat=previous_seat, seat=seat, reason=reason,
    )
    # `previous` is None when the old Adviser's account is gone: only the new
    # one has anyone to tell.
    transaction.on_commit(lambda: notify_adviser_replaced(
        record, replaced_by=actor, previous_adviser=previous, adviser=adviser,
    ))
    return {"adviser": {"id": adviser.pk, "name": _name(adviser)}, "seat": seat.pk}


# --- add an owner ---------------------------------------------------------------------

def add_owner(record: Record, email, *, actor) -> dict:
    """
    Add an existing, active, verified account as an owner of a paper in review.

    The Contact person does not change: the new owner is never primary. An
    account that does not qualify is one refusal, so it says nothing about
    whether the address is registered. The paper's Adviser cannot be added
    (IR-260).
    """
    from apps.accounts.models import User
    from apps.notifications.services import notify_owner_added

    _require_in_review(record)
    if not isinstance(email, str) or not email.strip():
        raise serializers.ValidationError({"email": NOT_A_MEMBER})
    owner = (
        User.objects.annotate(normalized_email=Lower("email"))
        .filter(normalized_email=email.strip().lower(), is_active=True, is_verified=True)
        .first()
    )
    if owner is None:
        raise serializers.ValidationError({"email": NOT_A_MEMBER})
    if owner.pk == record.adviser_id:
        raise serializers.ValidationError({"email": ADVISER_OWNS})
    if record.owners.filter(user=owner).exists():
        raise serializers.ValidationError({"email": ALREADY_AN_OWNER})

    try:
        with transaction.atomic():
            RecordOwner.objects.create(record=record, user=owner, is_primary=False)
    except IntegrityError:
        raise serializers.ValidationError({"email": ALREADY_AN_OWNER})

    audit.owner_added(record, actor, owner=owner)
    transaction.on_commit(lambda: notify_owner_added(record, added_by=actor, owner=owner))
    return {"owners": owners_payload(record)}


def owners_payload(record: Record) -> list[dict]:
    """The paper's owners, the Contact person first."""
    return [
        {"id": link.user_id, "name": _name(link.user), "is_primary": link.is_primary}
        for link in record.owners.select_related("user").order_by("-is_primary", "pk")
    ]


# --- withdraw the paper ---------------------------------------------------------------

def withdraw(record: Record, reason, *, actor) -> dict:
    """
    Withdraw a paper in review, with a required reason.

    The same path an owner's deletion takes: `soft_delete_record`, so
    `lifecycle.apply` moves the status and `reviews.withdrawal` closes every
    open assignment, seat, revision request and document request. The owners
    and the people whose work ends are told, after commit; the notice carries
    RDCO's reason. Like the owner's act, this deletes the paper.
    """
    from apps.notifications.services import notify_record_withdrawn
    from apps.reviews.withdrawal import open_review_work

    _require_in_review(record)
    reason = _text(reason, "reason", required=True, message=REASON_REQUIRED)
    # Read before the withdrawal closes it: whose work is ending.
    work = open_review_work(record)
    soft_delete_record(record, deleted_by=actor, reason=reason)
    transaction.on_commit(lambda: notify_record_withdrawn(
        record, withdrawn_by=actor, seats=work.seats,
        requesting_parties=work.requesting_parties, reason=reason,
    ))
    return {"id": record.pk, "withdrawn": True}
