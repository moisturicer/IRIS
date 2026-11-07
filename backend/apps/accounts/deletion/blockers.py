"""
What stops an account deletion being confirmed (ADR-051 §9, IR-785).

Confirmation is refused while somebody is waiting on the person:

- a paper in review that they own alone, which RDCO withdraws or gives another
  owner first (IR-797);
- an open review they hold, as an Adviser or office reviewer, which a
  coordinator reassigns, or RDCO replaces the Adviser, first.

A draft nobody else is waiting on doesn't block: it is deleted with the account.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db.models import Count

from core.enums import AssignmentState, OPEN_SEAT_STATES, Party, PipelineStatus, RoleName

SOLE_OWNER_IN_REVIEW = "sole_owner_in_review"
OPEN_REVIEW = "open_review"

# "RDCO", not the party label "RDCO Final": the office, not its stage.
_PARTY_LABELS = {Party.RDCO: str(RoleName.RDCO)}


def _party(party) -> str:
    return _PARTY_LABELS.get(party, str(Party(party).label))


@dataclass(frozen=True)
class Blocker:
    kind: str
    record: int
    title: str
    #: The plain-words reason, naming who clears it.
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


def blockers_for(user) -> list[Blocker]:
    from apps.records.models import Record
    from apps.reviews.models import RecordAssignment, ReviewerSeat

    found: list[Blocker] = []
    in_review = Record.objects.filter(pipeline_status=PipelineStatus.IN_REVIEW)

    # Counted apart from the filter on this person, which would join only their row.
    sole = (
        in_review.filter(pk__in=in_review.filter(owners__user=user).values("pk"))
        .annotate(n_owners=Count("owners", distinct=True))
        .filter(n_owners=1)
        .order_by("pk")
    )
    for record in sole:
        found.append(Blocker(
            SOLE_OWNER_IN_REVIEW, record.pk, record.title,
            f"“{record.title}” is in review and has no other owner. "
            "RDCO must withdraw it or add an owner.",
        ))

    held: set[tuple[int, str]] = set()
    seats = (
        ReviewerSeat.objects.filter(
            reviewer=user, state__in=OPEN_SEAT_STATES,
            assignment__state=AssignmentState.ACTIVE,
            assignment__record__in=in_review,
        )
        .select_related("assignment__record")
        .order_by("assignment__record_id", "pk")
    )
    adviser_waiting = (
        RecordAssignment.objects.filter(
            party=Party.ADVISER, state=AssignmentState.ACTIVE,
            record__in=in_review.filter(adviser=user),
        )
        .select_related("record")
        .order_by("record_id", "pk")
    )
    for assignment in [seat.assignment for seat in seats] + list(adviser_waiting):
        key = (assignment.record_id, str(assignment.party))
        if key in held:
            continue
        held.add(key)
        record = assignment.record
        who = (
            "RDCO must replace the Adviser."
            if assignment.party == Party.ADVISER
            else f"A {_party(assignment.party)} coordinator must reassign it."
        )
        found.append(Blocker(
            OPEN_REVIEW, record.pk, record.title,
            f"They hold an open {_party(assignment.party)} review on “{record.title}”. {who}",
        ))
    return found
