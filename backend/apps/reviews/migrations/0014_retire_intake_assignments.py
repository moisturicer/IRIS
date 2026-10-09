"""IR-260: move in-flight intake work to its named Adviser.

Historical intake assignments and reviews remain unchanged except that an open
intake assignment is withdrawn. Records without an eligible Adviser stay put
for explicit resolution; ``list_unassigned_intake`` reports them. Rollback
requires restoring the pre-migration database backup (ADR-032 §13).
"""

import uuid

from django.db import migrations
from django.utils import timezone


REASON = "ADR-032: intake retired"


def retire_intake(apps, schema_editor):
    Record = apps.get_model("records", "Record")
    RecordOwner = apps.get_model("records", "RecordOwner")
    RecordAssignment = apps.get_model("reviews", "RecordAssignment")
    ReviewerSeat = apps.get_model("reviews", "ReviewerSeat")
    RoutingEvent = apps.get_model("reviews", "RoutingEvent")

    for record in Record.objects.filter(pipeline_status="rdco_intake").order_by("pk").iterator():
        if not record.adviser_id or RecordOwner.objects.filter(
            record_id=record.pk, user_id=record.adviser_id
        ).exists():
            continue

        unexpected = list(RecordAssignment.objects.filter(
            record_id=record.pk, state="active"
        ).exclude(party__in=["intake", "adviser"]).values_list("party", flat=True))
        if unexpected:
            raise RuntimeError(
                f"Record {record.pk} is at intake but also held by {unexpected}; "
                "resolve the inconsistent assignment before migrating."
            )

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
        record.pipeline_status = "in_review"
        record.save(update_fields=["pipeline_status"])


def restore_backup(apps, schema_editor):
    raise RuntimeError(
        "IR-260 intake retirement cannot be reversed safely; restore the "
        "pre-migration database backup instead."
    )


class Migration(migrations.Migration):
    dependencies = [
        ("records", "0016_record_details_edited_at"),
        ("reviews", "0013_reviewerseat_closed_by_decision"),
    ]

    operations = [migrations.RunPython(retire_intake, restore_backup)]
