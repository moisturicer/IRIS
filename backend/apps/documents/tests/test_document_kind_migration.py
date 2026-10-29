"""Migration 0007's backfill, tested against rows that already exist (IR-239).

The field defaults to ``supplementary``, so a manuscript written before this
migration would silently drop out of the RAG corpus if the backfill were
wrong or absent — and it would do so invisibly, because a row with the wrong
``kind`` looks exactly like a row with the right one. That is the failure
this test exists to catch.

Mechanics follow ``apps/ai/tests/test_chunk_persistence_migration.py``: rewind
only this app, create data at the pre-migration state, migrate forward, read
the result. ``transaction=True`` is required because the migration executor
manages its own transactions, which do not compose with pytest-django's
per-test wrapping transaction.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.records.models import RecordType
from apps.reviews.workflow_test_helpers import model_at_current_state

pytestmark = [pytest.mark.db_required, pytest.mark.django_db(transaction=True)]

_MIGRATE_FROM = [("documents", "0006_pdfextraction_manuscript_extraction")]
_MIGRATE_TO = [("documents", "0007_pdfextraction_kind")]


def test_the_backfill_marks_existing_rows_from_the_owner_they_hang_off():
    executor = MigrationExecutor(connection)
    old_apps = executor.loader.project_state(_MIGRATE_FROM).apps
    executor.migrate(_MIGRATE_FROM)

    try:
        OldPdfExtraction = old_apps.get_model("documents", "PdfExtraction")
        OldUploadSlot = old_apps.get_model("documents", "UploadSlot")
        OldRecordUpload = old_apps.get_model("documents", "RecordUpload")

        # Cross-app dependencies can also rewind records. Match the schema
        # actually left applied, rather than the live model or target closure.
        record_type = RecordType.objects.create(name="Thesis")
        record = model_at_current_state("records", "Record").objects.create(
            title="Pre-existing thesis", record_type_id=record_type.pk,
        )

        slot = OldUploadSlot.objects.create(name="Ethics Clearance", record_type_id=record_type.pk)
        upload = OldRecordUpload.objects.create(
            record_id=record.pk, slot_id=slot.pk, file="documents/clearance.pdf"
        )

        manuscript = OldPdfExtraction.objects.create(record_id=record.pk, status="done")
        supplementary = OldPdfExtraction.objects.create(upload_id=upload.pk, status="done")

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATE_TO)
        new_apps = executor.loader.project_state(_MIGRATE_TO).apps
        NewPdfExtraction = new_apps.get_model("documents", "PdfExtraction")

        assert NewPdfExtraction.objects.get(pk=manuscript.pk).kind == "manuscript"
        assert NewPdfExtraction.objects.get(pk=supplementary.pk).kind == "supplementary"
    finally:
        call_command("migrate", verbosity=0)
