"""IR-872: existing versions get their documents reconstructed, and say so."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.reviews.workflow_test_helpers import purge_records_at_current_state

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]
BEFORE = [("records", "0030_details_revision_and_metadata_sources")]
AFTER = [("records", "0031_version_documents")]
MANILA = ZoneInfo("Asia/Manila")


def at(day):
    return datetime(2027, 3, day, 12, tzinfo=MANILA)


def test_each_old_version_names_the_newest_upload_before_it_and_is_flagged():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    try:
        executor = MigrationExecutor(connection)
        old = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        record_type = old.get_model("records", "RecordType").objects.get_or_create(name="Thesis / Research")[0]
        record = old.get_model("records", "Record").objects.create(
            title="Existing", pipeline_status="in_review", record_type_id=record_type.pk,
        )
        Slot = old.get_model("documents", "UploadSlot")
        consent = Slot.objects.create(name="Consent form", record_type_id=record_type.pk)
        approval = Slot.objects.create(name="Approval sheet", record_type_id=record_type.pk)
        Upload = old.get_model("documents", "RecordUpload")

        def upload(slot, version, day):
            row = Upload.objects.create(record_id=record.pk, slot_id=slot.pk, file="x.pdf", version=version)
            Upload.objects.filter(pk=row.pk).update(created_at=at(day))
            return row.pk

        c1 = upload(consent, 1, 1)
        c2 = upload(consent, 2, 5)      # after v1, before v2
        a1 = upload(approval, 1, 9)     # after v2: neither version names it
        Version = old.get_model("records", "RecordVersion")
        Version.objects.create(record_id=record.pk, number=1, cause="submission", created_at=at(2))
        Version.objects.create(record_id=record.pk, number=2, cause="revision", created_at=at(6))

        executor.migrate(AFTER)
        executor = MigrationExecutor(connection)
        new = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
        Doc = new.get_model("records", "RecordVersionDocument")
        named = {
            n: sorted(Doc.objects.filter(version__record_id=record.pk, version__number=n)
                      .values_list("upload_id", flat=True))
            for n in (1, 2)
        }
        assert named == {1: [c1], 2: [c2]}
        assert a1 not in Doc.objects.values_list("upload_id", flat=True)
        flags = new.get_model("records", "RecordVersion").objects.filter(record_id=record.pk) \
            .values_list("documents_reconstructed", flat=True)
        assert list(flags) == [True, True]
    finally:
        purge_records_at_current_state()
        call_command("migrate", verbosity=0)
