"""Give in-flight specialist records RDCO oversight without rewriting history."""
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import migrations
from django.utils import timezone

REASON = "Opened when RDCO began holding every routed Record (ADR-047)"


def forward(apps, schema_editor):
    alias = schema_editor.connection.alias
    Assignment = apps.get_model("reviews", "RecordAssignment")
    Event = apps.get_model("reviews", "RoutingEvent")
    Record = apps.get_model("records", "Record")
    Turnaround = apps.get_model("reviews", "Turnaround")
    Holiday = apps.get_model("reviews", "Holiday")
    assignments = Assignment.objects.using(alias)
    passed = assignments.filter(party="adviser", state="completed").values("record_id")
    active_adviser = assignments.filter(party="adviser", state="active").values("record_id")
    active_rdco = assignments.filter(party="rdco", state="active").values("record_id")
    records = Record.objects.using(alias).filter(
        pipeline_status="in_review", record_type__name__in=["Thesis / Research", "Project"],
        pk__in=passed,
    ).exclude(pk__in=active_adviser).exclude(pk__in=active_rdco)
    now = timezone.now()
    days = Turnaround.objects.using(alias).filter(party="rdco").values_list("working_days", flat=True).first()
    due = None
    if days is not None:
        day = now.astimezone(ZoneInfo("Asia/Manila")).date()
        holidays = set(Holiday.objects.using(alias).values_list("date", flat=True))
        remaining = days
        while remaining:
            day += timedelta(days=1)
            if day.weekday() < 5 and day not in holidays:
                remaining -= 1
        due = datetime.combine(day, time(23, 59), tzinfo=ZoneInfo("Asia/Manila"))
    for record in records.iterator():
        assignments.create(record_id=record.pk, party="rdco", state="active", reason=REASON,
                           opened_at=now, clock_started_at=now, due_at=due, original_due_at=due)
        Event.objects.using(alias).create(record_id=record.pk, from_party="adviser", to_party="rdco",
                                         reason=REASON, group_id=uuid.uuid4(), created_at=now)


def backward(apps, schema_editor):
    alias = schema_editor.connection.alias
    Assignment = apps.get_model("reviews", "RecordAssignment")
    Event = apps.get_model("reviews", "RoutingEvent")
    events = Event.objects.using(alias).filter(reason=REASON, actor__isnull=True)
    for event in events:
        rows = Assignment.objects.using(alias).filter(
            record_id=event.record_id, party="rdco", reason=REASON, opened_at=event.created_at,
        )
        for assignment in rows:
            if (assignment.state != "active" or assignment.seats.exists()
                    or assignment.reviews.exists() or assignment.extensions.exists()
                    or assignment.document_requests.exists() or assignment.resubmission_requests.exists()
                    or assignment.deadline_moments.exists()):
                raise RuntimeError("RDCO has acted on a cutover assignment; preserve its history before reversing ADR-047.")
            assignment.delete()
        event.delete()


class Migration(migrations.Migration):
    dependencies = [("reviews", "0022_rdco_executive_review")]
    operations = [migrations.RunPython(forward, backward)]
