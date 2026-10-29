"""IR-619 leaves old open/closed assignment history unchanged and undated."""
import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .workflow_test_helpers import purge_records_at_current_state

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
BEFORE = [("reviews", "0016_retire_rdco_intake_stage")]
AFTER = [("reviews", "0017_holiday_turnaround_recordassignment_clock_started_at_and_more")]


def test_existing_pool_closed_assignment_and_clearance_survive_undated():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    try:
        executor = MigrationExecutor(connection)
        # Only reviews was rewound; unaffected apps retain their actual
        # applied schema, including later non-null Record columns.
        old = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        record = old.get_model("records", "Record").objects.create(title="Existing review", pipeline_status="in_review")
        Assignment = old.get_model("reviews", "RecordAssignment")
        opened = Assignment.objects.create(record_id=record.pk, party="itso")
        closed = Assignment.objects.create(record_id=record.pk, party="ierc", state="completed", closed_at=timezone.now())
        clearance = old.get_model("reviews", "RecordClearance").objects.create(
            record_id=record.pk, office="ierc", status="cleared",
        )
        executor.migrate(AFTER)
        executor = MigrationExecutor(connection)
        new = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        rows = new.get_model("reviews", "RecordAssignment").objects.filter(record_id=record.pk)
        assert list(rows.values_list("id", "party", "state")) == [
            (opened.pk, "itso", "active"), (closed.pk, "ierc", "completed"),
        ]
        assert all(row.due_at is None and row.original_due_at is None
                   and row.clock_started_at is None and row.document_pause_started_at is None
                   for row in rows)
        assert new.get_model("reviews", "RecordClearance").objects.get(pk=clearance.pk).status == "cleared"
        assert new.get_model("reviews", "Turnaround").objects.count() == 0
    finally:
        purge_records_at_current_state()
        call_command("migrate", verbosity=0)
