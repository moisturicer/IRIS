"""Migration 0019 gives IRIS a notice and leaves every existing account unanswered (IR-789).

ADR-054 decision 17: existing accounts start unanswered and answer at next
sign-in. The migration must not mark anyone as having accepted version 1 --
not even an account whose legacy `consent_given` is true, which was a different,
unversioned fact. And it must leave a notice behind, so IRIS never runs without
one.

Mechanics follow ``test_session_end_reason_migration.py``.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("accounts", "0018_seed_system_admin_role")]
_MIGRATE_TO = [("accounts", "0019_data_notice_and_answers")]


def test_existing_accounts_start_unanswered_and_version_one_exists():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldUser = old_apps.get_model("accounts", "User")
        consented = OldUser.objects.create(email="old-yes@cit.edu", password="!", consent_given=True)
        never = OldUser.objects.create(email="old-no@cit.edu", password="!", consent_given=False)

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps
        NewUser = new_apps.get_model("accounts", "User")
        DataNotice = new_apps.get_model("accounts", "DataNotice")

        for pk in (consented.pk, never.pk):
            after = NewUser.objects.get(pk=pk)
            assert after.answered_notice_version is None
            assert after.ai_consent is None
            assert after.notice_answered_at is None
        # The legacy fact is kept as it was, and is not read as an answer.
        assert NewUser.objects.get(pk=consented.pk).consent_given is True

        version_one = DataNotice.objects.get(number=1)
        assert version_one.title and version_one.sections
        assert DataNotice.objects.count() == 1
    finally:
        call_command("migrate", verbosity=0)
