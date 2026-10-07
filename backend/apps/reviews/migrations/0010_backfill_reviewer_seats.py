"""
IR-415: one seat per existing active assignment, per ADR-032 §13.

- **Adviser** assignments seat `record.adviser` (`source=entry`), as
  submission now does.
- **ITSO / IERC / KTTO / RDCO** assignments seat the most recent person who
  reviewed the record for that party: a `Review` at its stage, or, for the
  three clearance offices, the person who signed its `RecordClearance`. In the
  old pipeline that person took the work up themselves, so the seat is
  `claimed`.
- **Everything else stays seatless**, which is the office's pool: an office
  nobody has reviewed for yet, and every `intake` assignment, since intake is
  retired (ADR-032 §1) and IR-260 withdraws those assignments.

A seat whose holder has already reviewed is `in_review`, opened at that review;
an Adviser who has not reviewed yet holds an `assigned` seat. Nothing is
invented: no reviewer is guessed, and no date is made up beyond the
assignment's own.

Written against the historical models and spelled out rather than imported
from `apps.reviews.seats`, for the reason `0008` gives: a migration must do the
same thing for as long as it exists. Assignments that already have a seat are
skipped -- the live code reached them first. Reversing is a no-op: reversing
`0009` drops the table.
"""

from django.db import migrations

#: The `Review.stage` each seated party is reviewed at. `intake` is absent on
#: purpose (module note).
STAGE_FOR_PARTY = {
    "adviser": "adviser",
    "itso": "itso",
    "ierc": "ierc",
    "ktto": "ktto",
    "rdco": "rdco",
}
CLEARANCE_OFFICES = {"itso", "ierc", "ktto"}


def _latest_reviewer(Review, RecordClearance, assignment):
    """(reviewer id, when) of the party's most recent review, or None."""
    party = assignment.party
    candidates = [
        (created_at, reviewer_id)
        for reviewer_id, created_at in Review.objects.filter(
            record_id=assignment.record_id, stage=STAGE_FOR_PARTY[party],
        ).values_list("reviewed_by_id", "created_at")
    ]
    if party in CLEARANCE_OFFICES:
        candidates += [
            (updated_at, reviewer_id)
            for reviewer_id, updated_at in RecordClearance.objects.filter(
                record_id=assignment.record_id, office=party, reviewed_by__isnull=False,
            ).values_list("reviewed_by_id", "updated_at")
        ]
    if not candidates:
        return None
    when, reviewer_id = max(candidates, key=lambda c: c[0])
    return reviewer_id, when


def backfill(apps, schema_editor):
    RecordAssignment = apps.get_model("reviews", "RecordAssignment")
    ReviewerSeat = apps.get_model("reviews", "ReviewerSeat")
    Review = apps.get_model("reviews", "Review")
    RecordClearance = apps.get_model("reviews", "RecordClearance")

    seats = []
    for assignment in (
        RecordAssignment.objects.filter(state="active", party__in=STAGE_FOR_PARTY)
        .exclude(seats__isnull=False)
        .select_related("record")
        .order_by("pk")
    ):
        party = assignment.party
        if party == "adviser":
            adviser_id = assignment.record.adviser_id
            if adviser_id is None:
                continue
            reviewed = (
                Review.objects.filter(
                    record_id=assignment.record_id, stage="adviser", reviewed_by_id=adviser_id,
                )
                .order_by("-created_at")
                .values_list("created_at", flat=True)
                .first()
            )
            seats.append(ReviewerSeat(
                assignment=assignment, reviewer_id=adviser_id, source="entry",
                state="in_review" if reviewed else "assigned",
                assigned_at=assignment.opened_at, opened_at=reviewed,
            ))
            continue

        latest = _latest_reviewer(Review, RecordClearance, assignment)
        if latest is None:
            continue  # the office's pool
        reviewer_id, when = latest
        seats.append(ReviewerSeat(
            assignment=assignment, reviewer_id=reviewer_id, source="claimed",
            state="in_review", assigned_at=when, opened_at=when,
        ))

    ReviewerSeat.objects.bulk_create(seats)


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0009_reviewer_seat"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
