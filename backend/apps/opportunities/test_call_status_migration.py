"""Migration 0003 confirms every existing Call (ADR-050 decision 8, IR-762).

Calls that exist when RDCO's confirmation ships were already public, so the
migration marks them confirmed; only Calls created after it start pending.
Mechanics follow ``test_call_fields_migration.py``.
"""

from datetime import date

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("opportunities", "0002_call_fields")]
_MIGRATE_TO = [("opportunities", "0003_call_status")]


def test_existing_calls_are_confirmed_and_new_ones_start_pending():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldOpportunity = old_apps.get_model("opportunities", "Opportunity")
        existing = OldOpportunity.objects.create(
            opportunity_type="conference", title="ICAC 2027", due_date=date(2026, 12, 1),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        Opportunity = executor.loader.project_state(_MIGRATE_TO).apps.get_model("opportunities", "Opportunity")

        moved = Opportunity.objects.get(pk=existing.pk)
        assert (moved.status, moved.review_reason, moved.reviewed_at) == ("confirmed", "", None)
        fresh = Opportunity.objects.create(
            opportunity_type="conference", title="Later", due_date=date(2026, 12, 2),
        )
        assert fresh.status == "pending"

        # Reversing drops the columns and keeps the Calls.
        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_FROM)
        assert OldOpportunity.objects.count() == 2
    finally:
        call_command("migrate", verbosity=0)
