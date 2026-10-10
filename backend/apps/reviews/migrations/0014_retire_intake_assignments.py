"""IR-260: contract the shadow workflow into the adviser-first model.

Historical intake assignments and reviews remain unchanged except that an open
intake assignment is withdrawn. Records without an eligible Adviser block the
cutover; ``list_unassigned_intake`` reports them for a person to resolve. Rollback
requires restoring the pre-migration database backup (ADR-032 §13).
"""

import uuid

from django.db import migrations
from django.utils import timezone


REASON = "ADR-032: intake retired"
IN_FLIGHT = {
    "adviser_review", "rdco_intake", "itso_review", "parallel_review",
    "rdco_review", "declined",
}
STAGE_TO_PARTY = {"rdco_intake": "intake", "intake": "intake"}


def _expected(record, reviews, clearances):
    """The frozen §6 shadow mapping; never import mutable application code."""
    status = record.pipeline_status
    pending = {c.office for c in clearances if c.status == "pending"}
    cleared = {c.office for c in clearances if c.status == "cleared"}
    if status == "adviser_review":
        return {"adviser"}, set(), None
    if status == "rdco_intake":
        return {"intake"}, set(), None
    if status in ("itso_review", "parallel_review"):
        return pending, {"intake", *cleared}, None
    if status == "rdco_review":
        return {"rdco"}, {"intake", *cleared}, None
    if status == "declined":
        declines = [review for review in reviews if review.status == "declined"]
        if not declines:
            raise ValueError("declined record has no decline review")
        decline = declines[-1]
        requester = STAGE_TO_PARTY.get(decline.stage, decline.stage)
        passed_intake = requester != "intake" and any(
            review.stage in ("rdco_intake", "intake")
            and review.status == "approved" for review in reviews
        )
        completed = cleared - {requester}
        if passed_intake:
            completed.add("intake")
        return {requester} | pending, completed, decline
    raise ValueError(f"unknown in-flight status {status!r}")


def _preflight(Record, RecordOwner, RecordAssignment, Review,
               RecordClearance, ResubmissionRequest):
    """Report all inconsistent IDs before changing any record."""
    failures = []
    for record in Record.objects.filter(pipeline_status__in=IN_FLIGHT).order_by("pk").iterator():
        reviews = list(Review.objects.filter(record_id=record.pk).order_by("created_at", "pk"))
        clearances = list(RecordClearance.objects.filter(record_id=record.pk))
        assignments = list(RecordAssignment.objects.filter(record_id=record.pk))
        try:
            active, completed, decline = _expected(record, reviews, clearances)
            if not active:
                raise ValueError("in-flight record has no active party")
            held = {a.party for a in assignments if a.state == "active"}
            history = {a.party for a in assignments if a.state == "completed"}
            if held != active:
                raise ValueError(f"active assignments {sorted(held)} != {sorted(active)}")
            if not completed <= history:
                raise ValueError(f"missing completed assignments {sorted(completed - history)}")
            if decline and not ResubmissionRequest.objects.filter(
                record_id=record.pk, review_id=decline.pk,
                party=STAGE_TO_PARTY.get(decline.stage, decline.stage), state="open",
            ).exists():
                raise ValueError("decline has no open resubmission request")
            if "intake" in held and (
                not record.adviser_id or RecordOwner.objects.filter(
                    record_id=record.pk, user_id=record.adviser_id,
                ).exists()
            ):
                raise ValueError("intake needs an eligible Adviser")
        except ValueError as exc:
            failures.append(f"{record.pk} ({exc})")
    if failures:
        raise RuntimeError("IR-260 preflight failed for Record ids: " + "; ".join(failures))


def retire_intake(apps, schema_editor):
    Record = apps.get_model("records", "Record")
    RecordOwner = apps.get_model("records", "RecordOwner")
    RecordAssignment = apps.get_model("reviews", "RecordAssignment")
    Review = apps.get_model("reviews", "Review")
    RecordClearance = apps.get_model("reviews", "RecordClearance")
    ReviewerSeat = apps.get_model("reviews", "ReviewerSeat")
    RoutingEvent = apps.get_model("reviews", "RoutingEvent")
    ResubmissionRequest = apps.get_model("reviews", "ResubmissionRequest")
    DocumentRequest = apps.get_model("documents", "DocumentRequest")

    _preflight(Record, RecordOwner, RecordAssignment, Review,
               RecordClearance, ResubmissionRequest)

    intake_ids = set(RecordAssignment.objects.filter(
        party="intake", state="active"
    ).values_list("record_id", flat=True))
    intake_ids.update(Record.objects.filter(
        pipeline_status="rdco_intake"
    ).values_list("pk", flat=True))
    for record in Record.objects.filter(pk__in=intake_ids).order_by("pk").iterator():
        now = timezone.now()
        intake = RecordAssignment.objects.filter(
            record_id=record.pk, party="intake", state="active"
        ).first()
        if intake:
            intake.state = "withdrawn"
            intake.closed_at = now
            intake.reason = REASON
            intake.save(update_fields=["state", "closed_at", "reason"])
            ReviewerSeat.objects.filter(assignment_id=intake.pk).exclude(
                state__in=["done", "withdrawn"]
            ).update(state="withdrawn")
            # A retired party cannot keep asking the owner for work. Preserve
            # each request as withdrawn history, without attributing it to the
            # incoming Adviser.
            ResubmissionRequest.objects.filter(
                assignment_id=intake.pk, state="open"
            ).update(state="withdrawn", resolved_at=now)
            DocumentRequest.objects.filter(
                assignment_id=intake.pk, state="open"
            ).update(state="withdrawn", closed_at=now)

        adviser, created = RecordAssignment.objects.get_or_create(
            record_id=record.pk, party="adviser", state="active",
            defaults={"opened_at": now, "reason": REASON},
        )
        if not ReviewerSeat.objects.filter(
            assignment_id=adviser.pk, reviewer_id=record.adviser_id
        ).exclude(state="withdrawn").exists():
            ReviewerSeat.objects.create(
                assignment_id=adviser.pk, reviewer_id=record.adviser_id,
                state="assigned", source="entry", assigned_at=now,
            )
        if created:
            RoutingEvent.objects.create(
                record_id=record.pk, from_party="intake", to_party="adviser",
                reason=REASON, group_id=uuid.uuid4(), created_at=now,
            )
    Record.objects.filter(pipeline_status__in=IN_FLIGHT).update(pipeline_status="in_review")


def restore_backup(apps, schema_editor):
    """
    Refuse to reverse whenever there is anything the forward step may have
    changed: a record at `in_review` (a converted legacy status is
    indistinguishable from a native one) or an assignment it opened or
    withdrew. Only a database holding neither -- an empty one, as a migration
    test rewinds -- has nothing to put back, and reverses as a no-op.
    """
    Record = apps.get_model("records", "Record")
    RecordAssignment = apps.get_model("reviews", "RecordAssignment")
    if (
        Record.objects.filter(pipeline_status="in_review").exists()
        or RecordAssignment.objects.filter(reason=REASON).exists()
    ):
        raise RuntimeError(
            "IR-260 intake retirement cannot be reversed safely; restore the "
            "pre-migration database backup instead."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0011_documentrequest_closed_by_decision"),
        ("records", "0016_record_details_edited_at"),
        ("reviews", "0013_reviewerseat_closed_by_decision"),
    ]

    operations = [migrations.RunPython(retire_intake, restore_backup)]
