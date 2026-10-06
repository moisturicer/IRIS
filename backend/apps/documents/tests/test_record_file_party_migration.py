"""Migration 0010's backfill of `RecordFile.party` (IR-476, decision 7).

A file belongs to the office that filed it, and only that office may remove
it. Rows that predate the field are filled from the uploader's *current* role.
A row whose uploader is gone, or was never an office, stays null: no office
can remove it, and only the admin escape hatch can.

Mechanics follow ``test_document_kind_migration.py``: rewind only this app,
create rows at the pre-migration state, migrate forward, read the result.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.accounts.models import Role, User
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("documents", "0009_document_request_decisions")]
_MIGRATE_TO = [("documents", "0010_recordfile_party")]


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test", last_name="User",
        role=role, is_verified=True,
    )


def test_the_backfill_fills_the_party_from_the_uploaders_current_role():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldRecordFile = old_apps.get_model("documents", "RecordFile")

        # Users and the record through the current models: only `documents`
        # is rewound, so the other apps' tables keep their latest schema.
        # `get_or_create`, because an earlier TransactionTestCase flush can
        # have removed the migration-seeded RecordType.
        record_type, _ = RecordType.objects.get_or_create(name="Thesis / Research")
        owner = _user("backfill-owner@cit.edu", "Student")
        record = Record.objects.create(
            title="Pre-existing disclosure", record_type=record_type, added_by=owner,
        )

        uploaders = {
            "itso": _user("backfill-itso@cit.edu", "ITSO"),
            "ierc": _user("backfill-ierc@cit.edu", "IERC"),
            "ktto": _user("backfill-ktto@cit.edu", "KTTO"),
            "rdco": _user("backfill-rdco@cit.edu", "RDCO"),
            None:   owner,  # not an office
        }
        rows = {
            party: OldRecordFile.objects.create(
                record_id=record.pk, file=f"record_files/{party}.txt",
                filename=f"{party}.txt", uploaded_by_id=user.pk,
            )
            for party, user in uploaders.items()
        }
        no_uploader = OldRecordFile.objects.create(
            record_id=record.pk, file="record_files/orphan.txt", filename="orphan.txt",
            uploaded_by_id=None,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps
        NewRecordFile = new_apps.get_model("documents", "RecordFile")

        for party, row in rows.items():
            assert NewRecordFile.objects.get(pk=row.pk).party == party, party
        assert NewRecordFile.objects.get(pk=no_uploader.pk).party is None
    finally:
        call_command("migrate", verbosity=0)
