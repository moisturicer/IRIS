"""Rebuild every paper's views from `ACCESS` history (IR-369).

Until now `Record.access_count` rose on every page load, by anyone, on any
paper. After this a view is one account's first opening of a published paper
(CONTEXT.md **View**), so the old numbers are replaced, not adjusted:

- one view per distinct account per published paper, from its `ACCESS` events;
- never the paper's owners (as owned today), never an event with no account;
- an account deleted since still counts, but no row is stored for it: that is
  what deleting an account does to a view it made (decided 2026-11-12);
- dated by that account's earliest opening after publication. Publication is
  the paper's first `PUBLISHED` audit event, which exists only for papers
  published since IR-144; a paper with none counts every opening it has;
- a published paper whose delete request is still awaiting review counts as
  published, because declining the request restores it. Any other paper,
  including one whose deletion was approved, has no views.

Reversing drops the rows and keeps the rebuilt counts: the per-load numbers
can't be recovered, and nothing should need them.
"""

from django.db import migrations
from django.db.models import Min

PUBLISHED = "published"
PENDING_DELETE = "pending_delete"
PENDING = "pending"


def rebuild_views(apps, schema_editor):
    Record = apps.get_model("records", "Record")
    RecordOwner = apps.get_model("records", "RecordOwner")
    RecordView = apps.get_model("records", "RecordView")
    DeleteRequest = apps.get_model("records", "DeleteRequest")
    AuditEvent = apps.get_model("audit", "AuditEvent")
    User = apps.get_model("accounts", "User")

    RecordView.objects.all().delete()

    awaiting_deletion = set(
        DeleteRequest.objects.filter(
            status=PENDING, previous_pipeline_status=PUBLISHED,
            record__pipeline_status=PENDING_DELETE, record__is_deleted=False,
        ).values_list("record_id", flat=True)
    )
    published = set(
        Record._base_manager.filter(pipeline_status=PUBLISHED, is_deleted=False)
        .values_list("pk", flat=True)
    ) | awaiting_deletion
    Record._base_manager.exclude(pk__in=published).exclude(access_count=0).update(access_count=0)

    published_at = dict(
        AuditEvent.objects.filter(event_type="PUBLISHED", record_id__in=published)
        .values("record_id").annotate(at=Min("created_at")).values_list("record_id", "at")
    )
    owners = set(RecordOwner.objects.filter(record_id__in=published).values_list("record_id", "user_id"))
    accounts = dict(User.objects.values_list("pk", "deleted_at"))

    first_openings = {}
    openings = (
        AuditEvent.objects.filter(event_type="ACCESS", record_id__in=published, user_id__isnull=False)
        .values_list("record_id", "user_id", "created_at")
    )
    for record_id, user_id, at in openings.iterator():
        if user_id not in accounts or (record_id, user_id) in owners:
            continue
        since = published_at.get(record_id)
        if since is not None and at < since:
            continue
        key = (record_id, user_id)
        if key not in first_openings or at < first_openings[key]:
            first_openings[key] = at

    RecordView.objects.bulk_create(
        [
            RecordView(record_id=r, user_id=u, viewed_at=at)
            for (r, u), at in first_openings.items()
            if accounts[u] is None
        ],
        batch_size=1000,
    )
    counts = {}
    for record_id, _user_id in first_openings:
        counts[record_id] = counts.get(record_id, 0) + 1
    for record_id in published:
        Record._base_manager.filter(pk=record_id).update(access_count=counts.get(record_id, 0))


def forget_views(apps, schema_editor):
    apps.get_model("records", "RecordView").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("records", "0039_record_view"),
        ("audit", "0026_unverified_registration_events"),
        ("accounts", "0022_data_notice_text"),
    ]

    operations = [migrations.RunPython(rebuild_views, forget_views)]
