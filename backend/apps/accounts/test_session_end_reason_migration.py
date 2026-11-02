"""Migration 0013 adds `UserSession.ended_reason` over rows that already exist (IR-645).

No backfill, on purpose: whether a session ended before this idled out or
logged out cannot be known. So a live session and an ended one both come
through with a null reason, and an ended one keeps its `ended_at` -- it must
not come back to life, and it reads as idle, the message it had before.

Mechanics follow ``apps/documents/tests/test_document_kind_migration.py``.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("accounts", "0012_reset_seeded_reference_sequences")]
_MIGRATE_TO = [("accounts", "0013_usersession_ended_reason")]


def test_existing_sessions_keep_their_state_and_get_no_reason():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldUserSession = old_apps.get_model("accounts", "UserSession")
        # Recovery adds a User column after this historical schema. Use its
        # historical User too, so this fixture never writes a future column.
        OldUser = old_apps.get_model("accounts", "User")
        user = OldUser.objects.create(email="pre@cit.edu", password="!")
        now = timezone.now()
        live = OldUserSession.objects.create(user_id=user.pk, created_at=now, last_activity_at=now)
        ended = OldUserSession.objects.create(
            user_id=user.pk, created_at=now - timedelta(hours=1),
            last_activity_at=now - timedelta(hours=1), ended_at=now - timedelta(minutes=20),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        NewUserSession = executor.loader.project_state(_MIGRATE_TO).apps.get_model("accounts", "UserSession")

        after_live = NewUserSession.objects.get(pk=live.pk)
        after_ended = NewUserSession.objects.get(pk=ended.pk)
        assert after_live.ended_at is None and after_live.ended_reason is None
        assert after_ended.ended_at == ended.ended_at and after_ended.ended_reason is None
    finally:
        call_command("migrate", verbosity=0)
