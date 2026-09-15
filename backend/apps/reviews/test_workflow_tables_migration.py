"""
IR-256's migrations, applied over rows that already exist.

`reviews/0007` adds the reviewer-directed routing tables, the nullable
`Review.assignment` link, the new choice values, and widens
`RecordClearance.status` from 10 to 20 characters for `not_cleared`.
`records/0012` adds `in_review` to `Record.pipeline_status`'s choices and
emits no SQL. Nothing in either may touch an existing Record, review or
clearance, and that is what this test checks: it snapshots those rows at the
pre-migration state, migrates forward, and compares.

**Two migrations, not one.** IR-256's first criterion asks for one. A Django
migration cannot alter another app's model, and `in_review` belongs to
`records`. So there is one migration per app, and the `records` one is
choices-only.

Mechanics follow `apps/documents/tests/test_document_kind_migration.py` and
`apps/ai/tests/test_embedding_space_migration.py`: rewind only the apps being
migrated, and write rows for *other* apps through their current models. The
rows here are the shape the thesis contribution depends on: a Record declined
by one office, with its peers' clearances already cleared.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.models import Role, User

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [
    ("records", "0011_record_dpa_accepted_at_record_dpa_accepted_by"),
    ("reviews", "0006_alter_recordauthpin_pin_alter_recordclearance_id"),
]
_MIGRATE_TO = [
    ("records", "0012_pipeline_status_in_review"),
    ("reviews", "0007_reviewer_directed_routing_tables"),
]

#: Every column of the three tables as it existed before the migration.
_SNAPSHOT_SQL = {
    "records_record": "SELECT * FROM records_record ORDER BY id",
    "reviews_review": (
        "SELECT id, record_id, reviewed_by_id, stage, status, comment, created_at "
        "FROM reviews_review ORDER BY id"
    ),
    "reviews_recordclearance": (
        "SELECT id, record_id, office, status, reviewed_by_id, comment, created_at, updated_at "
        "FROM reviews_recordclearance ORDER BY id"
    ),
}


def _snapshot():
    with connection.cursor() as cursor:
        rows = {}
        for table, sql in _SNAPSHOT_SQL.items():
            cursor.execute(sql)
            rows[table] = cursor.fetchall()
        return rows


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", role=role, is_verified=True
    )


def test_the_routing_tables_migrate_in_without_changing_any_existing_row():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldRecord = old_apps.get_model("records", "Record")
        OldRecordType = old_apps.get_model("records", "RecordType")
        OldReview = old_apps.get_model("reviews", "Review")
        OldRecordClearance = old_apps.get_model("reviews", "RecordClearance")

        owner = _user("ir256-mig-owner@cit.edu", "Student")
        rdco = _user("ir256-mig-rdco@cit.edu", "RDCO")
        offices = {office: _user(f"ir256-mig-{office}@cit.edu", office.upper())
                   for office in ("itso", "ierc", "ktto")}

        # get_or_create, not get: a TransactionTestCase earlier in the run
        # flushes the database, which removes the rows records/0002 seeds.
        project = OldRecordType.objects.get_or_create(name="Project")[0]
        thesis = OldRecordType.objects.get_or_create(name="Thesis / Research")[0]

        record = OldRecord.objects.create(
            title="Declined by IERC, peers cleared",
            record_type=project,
            added_by_id=owner.pk,
            pipeline_status="declined",
            requested_itso=True, requested_ierc=True, requested_ktto=True,
            resubmission_count=1,
        )
        published = OldRecord.objects.create(
            title="Published",
            record_type=thesis,
            added_by_id=owner.pk,
            pipeline_status="published",
        )

        OldReview.objects.create(
            record_id=record.pk, reviewed_by_id=rdco.pk, stage="rdco_intake", status="approved"
        )
        for office, decision in (("itso", "approved"), ("ktto", "approved"), ("ierc", "declined")):
            OldReview.objects.create(
                record_id=record.pk, reviewed_by_id=offices[office].pk,
                stage=office, status=decision, comment=f"{office} {decision}",
            )
            OldRecordClearance.objects.create(
                record_id=record.pk, office=office, reviewed_by_id=offices[office].pk,
                status="cleared" if decision == "approved" else "declined",
            )
        OldReview.objects.create(
            record_id=published.pk, reviewed_by_id=rdco.pk, stage="rdco", status="approved"
        )

        before = _snapshot()
        assert len(before["reviews_review"]) == 5
        assert len(before["reviews_recordclearance"]) == 3

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps

        assert _snapshot() == before

        # The link is there, and empty on every review that predates it.
        NewReview = new_apps.get_model("reviews", "Review")
        assert NewReview.objects.filter(assignment__isnull=False).count() == 0

        # The new tables exist and nothing was backfilled into them. That is IR-257.
        for model in ("RecordAssignment", "RoutingEvent", "ResubmissionRequest"):
            assert new_apps.get_model("reviews", model).objects.count() == 0

        # The widened column holds the new value, and the partial constraint is live.
        NewRecordClearance = new_apps.get_model("reviews", "RecordClearance")
        clearance = NewRecordClearance.objects.get(record_id=record.pk, office="ierc")
        clearance.status = "not_cleared"
        clearance.save(update_fields=["status"])
        assert NewRecordClearance.objects.get(pk=clearance.pk).status == "not_cleared"

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
                ["one_active_assignment_per_record_party"],
            )
            (indexdef,) = cursor.fetchone()
        assert "UNIQUE" in indexdef and "WHERE" in indexdef and "active" in indexdef
    finally:
        call_command("migrate", verbosity=0)
