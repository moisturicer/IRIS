"""Migration 0025 leaves every existing paper unanswered (ADR-052 §15, IR-811).

No default and no backfill. A published, consented paper with no IP mark is the
row a careless default would clear, so it is the row this checks: nobody has
said it may be sent, so it stays refused until someone does.

Mechanics follow ``apps/accounts/test_session_end_reason_migration.py``.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.ai.policy import Reason, decision_for_record
from apps.records.models import Record
from core.enums import EmbargoState, PipelineStatus

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("records", "0024_delete_budget_and_collaboration")]
_MIGRATE_TO = [("records", "0025_record_embargo")]


def test_existing_papers_come_through_unanswered_and_refused():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldRecord = old_apps.get_model("records", "Record")
        published = OldRecord.objects.create(
            title="Published and consented", abstract="An abstract.", is_ip=False,
            pipeline_status=PipelineStatus.PUBLISHED, dpa_accepted_at=timezone.now(),
        )
        draft = OldRecord.objects.create(
            title="A draft", abstract="An abstract.", pipeline_status=PipelineStatus.DRAFT,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        MigratedRecord = executor.loader.project_state(_MIGRATE_TO).apps.get_model("records", "Record")

        for pk in (published.pk, draft.pk):
            # Read exactly the schema under test, then exercise the live
            # derived policy in memory without querying newer columns.
            record = Record(**MigratedRecord.objects.filter(pk=pk).values().get())
            assert record.embargo_state == EmbargoState.UNKNOWN
            assert record.embargo_answered_at is None
            assert record.embargo_answered_by is None
            assert record.embargoed_until is None
            assert record.embargo_released_at is None
            assert record.embargo_released_by is None

        decision = decision_for_record(Record(**MigratedRecord.objects.filter(pk=published.pk).values().get()))
        assert decision.allowed is False
        assert decision.reasons == (Reason.EMBARGO_UNKNOWN,)
    finally:
        call_command("migrate", verbosity=0)
