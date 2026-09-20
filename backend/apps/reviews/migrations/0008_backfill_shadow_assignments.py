"""
IR-257: give every Record that predates the dual-write its shadow rows, once.

Implements §6 of `docs/workflow_routing_architecture.md` over the historical
models. The mapping is written out here rather than imported from
`apps.reviews.shadow`: a migration must do the same thing for as long as it
exists, and the live code will change (IR-260 rewrites it). Each reading of §6
is checked against the document by its own test
(`test_shadow_backfill_migration.py`, `test_shadow_assignments.py`), not by
sharing code.

**What this does not do, deliberately:**

- **No `RoutingEvent`.** The old model never recorded who sent a record where,
  so there is nothing true to backfill. The tracker says routing history starts
  at this migration.
- **No invented dates.** A completed assignment is dated from the reviews
  recorded at that party's stage; an active office's from its clearance row.
  Where no timestamp exists the row takes the migration time, and every row says
  it was backfilled.
- **No guessing.** A declined Record with no decline on record raises, naming
  it, rather than attributing the request to someone (§7.1's rule).

Records that already have an assignment are skipped: the dual-write reached
them first, and its rows are the truer ones.
"""

from django.db import migrations
from django.utils import timezone

MARKER = "backfilled from review history (IR-257)"

#: `Review.stage` -> party. `rdco_intake` is the stored stage IR-260 renames.
STAGE_TO_PARTY = {
    "adviser": "adviser",
    "rdco_intake": "intake",
    "intake": "intake",
    "itso": "itso",
    "ierc": "ierc",
    "ktto": "ktto",
    "rdco": "rdco",
}

#: Statuses nobody holds any more: §6's last row.
FINISHED = {"approved", "completed", "published", "rejected", "pending_delete"}


def _mapping(record, reviews, clearances):
    """(active parties, completed parties, the decline that is still open)."""
    status = record.pipeline_status
    pending = sorted(o for o, c in clearances.items() if c.status == "pending")
    cleared = sorted(o for o, c in clearances.items() if c.status == "cleared")

    if status == "adviser_review":
        return ["adviser"], [], None
    if status == "rdco_intake":
        return ["intake"], [], None
    if status in ("itso_review", "parallel_review"):
        return pending, ["intake", *cleared], None
    if status == "rdco_review":
        return ["rdco"], ["intake", *cleared], None
    if status == "declined":
        declines = [r for r in reviews if r.status == "declined"]
        if not declines:
            raise RuntimeError(
                f"Record {record.pk} is declined but has no decline review, so "
                f"there is no telling who asked for changes. Fix the record and "
                f"re-run; the backfill does not guess."
            )
        decline = declines[-1]
        requester = STAGE_TO_PARTY[decline.stage]
        active = [requester, *(o for o in pending if o != requester)]
        passed_intake = requester != "intake" and any(
            r.stage == "rdco_intake" and r.status == "approved" for r in reviews
        )
        completed = (["intake"] if passed_intake else []) + [
            o for o in cleared if o not in active
        ]
        return active, completed, decline
    if status in FINISHED:
        parties = []
        for review in reviews:
            party = STAGE_TO_PARTY[review.stage]
            if party not in parties:
                parties.append(party)
        return [], parties, None
    raise RuntimeError(
        f"Record {record.pk} has pipeline_status {status!r}, which §6 does not map."
    )


def backfill(apps, schema_editor):
    Record = apps.get_model("records", "Record")
    Review = apps.get_model("reviews", "Review")
    RecordClearance = apps.get_model("reviews", "RecordClearance")
    RecordAssignment = apps.get_model("reviews", "RecordAssignment")
    ResubmissionRequest = apps.get_model("reviews", "ResubmissionRequest")

    now = timezone.now()
    reached = RecordAssignment.objects.values_list("record_id", flat=True)
    records = (
        Record.objects.exclude(pk__in=reached)
        .exclude(pipeline_status="draft")
        .order_by("pk")
    )

    for record in records.iterator():
        reviews = list(Review.objects.filter(record_id=record.pk).order_by("created_at", "pk"))
        clearances = {c.office: c for c in RecordClearance.objects.filter(record_id=record.pk)}
        active, completed, decline = _mapping(record, reviews, clearances)

        by_party = {}
        for review in reviews:
            by_party.setdefault(STAGE_TO_PARTY[review.stage], []).append(review)

        for party in completed:
            at_stage = by_party.get(party)
            clearance = clearances.get(party)
            if at_stage:
                opened, closed = at_stage[0].created_at, at_stage[-1].created_at
                closed_by = at_stage[-1].reviewed_by_id
            elif clearance is not None:
                opened = closed = clearance.updated_at
                closed_by = clearance.reviewed_by_id
            else:
                opened, closed, closed_by = now, now, None
            RecordAssignment.objects.create(
                record_id=record.pk, party=party, state="completed",
                opened_at=opened, closed_at=closed, closed_by_id=closed_by,
                reason=MARKER,
            )

        held = {}
        for party in active:
            clearance = clearances.get(party)
            held[party] = RecordAssignment.objects.create(
                record_id=record.pk, party=party, state="active",
                opened_at=clearance.created_at if clearance is not None else now,
                reason=MARKER,
            )

        if decline is not None:
            party = STAGE_TO_PARTY[decline.stage]
            ResubmissionRequest.objects.create(
                record_id=record.pk, party=party, assignment=held[party],
                review_id=decline.pk, requested_by_id=decline.reviewed_by_id,
                reason=decline.comment, state="open", created_at=decline.created_at,
            )


def unbackfill(apps, schema_editor):
    """Remove what `backfill` wrote: its assignments and the requests on them."""
    RecordAssignment = apps.get_model("reviews", "RecordAssignment")
    ResubmissionRequest = apps.get_model("reviews", "ResubmissionRequest")
    ResubmissionRequest.objects.filter(assignment__reason=MARKER).delete()
    RecordAssignment.objects.filter(reason=MARKER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0012_pipeline_status_in_review"),
        ("reviews", "0007_reviewer_directed_routing_tables"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
