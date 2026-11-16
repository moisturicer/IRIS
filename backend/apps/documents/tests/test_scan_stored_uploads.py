"""
`scan_stored_uploads`: files stored before scanning are scanned once, and any
that fails is taken out of use (IR-666, ADR-072 decision 4).
"""
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditEvent
from apps.documents.models import RecordFile
from apps.documents.scanning import EICAR, FILE_GONE, FakeScanner, use_scanner
from apps.documents.tests import test_record_document_authorization as _authorization
from apps.notifications.models import Notification
from apps.records.models import Record, RecordOwner, RecordType, RecordVersion
from core.enums import VersionCause

make_user = _authorization.RecordDocumentAuthorizationTests.make_user


class ScanStoredUploadsTests(APITestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="iris-media-")
        self.quarantine = tempfile.mkdtemp(prefix="iris-quarantine-")
        settings = override_settings(MEDIA_ROOT=self.media, QUARANTINE_ROOT=self.quarantine)
        settings.enable()
        self.addCleanup(settings.disable)
        self.addCleanup(shutil.rmtree, self.media, True)
        self.addCleanup(shutil.rmtree, self.quarantine, True)

        self.owner = make_user("stored-owner@cit.edu", "Student")
        self.itso = make_user("stored-itso@cit.edu", "ITSO")
        self.rdco = make_user("stored-rdco@cit.edu", "RDCO")
        self.record = Record.objects.create(
            title="An old submission", abstract="D" * 40, record_type=RecordType.objects.first(),
            added_by=self.owner, pipeline_status="in_review",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        # An infected Manuscript, named by the Record and by its first version.
        self.record.abstract_file.save("old.pdf", ContentFile(EICAR), save=True)
        self.manuscript = self.record.abstract_file.name
        self.version = RecordVersion.objects.create(
            record=self.record, number=1, manuscript=self.manuscript, cause=VersionCause.SUBMISSION, created_by=self.owner,
        )
        # An infected office attachment, and a clean one.
        self.bad = RecordFile.objects.create(record=self.record, filename="memo.com", uploaded_by=self.itso,
                                             file=ContentFile(EICAR, name="memo.com"))
        self.good = RecordFile.objects.create(record=self.record, filename="notes.txt", uploaded_by=self.itso,
                                              file=ContentFile(b"office notes", name="notes.txt"))

    def run_command(self, *args):
        out = StringIO()
        call_command("scan_stored_uploads", *args, stdout=out)
        return out.getvalue()

    def test_a_dry_run_reports_and_changes_nothing(self):
        out = self.run_command("--dry-run")
        self.assertIn("3 stored file(s): 1 clean, 2 would be quarantined", out)
        self.bad.refresh_from_db()
        self.assertTrue(self.bad.file)
        self.assertEqual(list(Path(self.quarantine).iterdir()), [])
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.FILE_QUARANTINED).exists())

    def test_failing_files_leave_use_their_rows_stay_and_everyone_is_told(self):
        with self.captureOnCommitCallbacks(execute=True):
            out = self.run_command()
        self.assertIn("3 stored file(s): 1 clean, 2 quarantined", out)

        # Kept for inspection, outside the media folder; gone from storage.
        self.assertEqual(sorted(p.read_bytes() for p in Path(self.quarantine).iterdir()), [EICAR, EICAR])
        self.assertFalse((Path(self.media) / self.manuscript).exists())

        # Rows stay, without the file. The clean one is untouched.
        self.bad.refresh_from_db()
        self.good.refresh_from_db()
        self.record.refresh_from_db()
        self.version.refresh_from_db()
        self.assertFalse(self.bad.file)
        self.assertTrue(self.good.file)
        self.assertFalse(self.record.abstract_file)
        self.assertFalse(self.version.manuscript)

        events = AuditEvent.objects.filter(event_type=AuditEvent.FILE_QUARANTINED)
        self.assertEqual(
            sorted((e.metadata["model"], e.metadata["field"]) for e in events),
            [("documents.RecordFile", "file"), ("records.Record", "abstract_file"),
             ("records.RecordVersion", "manuscript")],
        )
        self.assertTrue(all(e.metadata["signature"] == "Eicar-Test-Signature" for e in events))

        told = Notification.objects.filter(notif_type__name="File Quarantined")
        self.assertTrue(told.filter(recipient=self.owner, message__contains="The manuscript").exists())
        self.assertTrue(told.filter(recipient=self.itso, message__contains='"memo.com"').exists())
        self.assertTrue(told.filter(broadcast_to_role__name="RDCO").exists())

    def test_what_iris_read_from_a_quarantined_manuscript_is_taken_out_of_use(self):
        from apps.ai.models import ChunkSet
        from apps.documents.models import PdfExtraction

        PdfExtraction.objects.create(
            record=self.record, status="done", source_file=self.manuscript,
            extracted_text="text read from the flagged file",
        )
        chunks = ChunkSet.objects.create(
            record=self.record, extraction_hash="e", strategy_id="s", options={},
            content_hash="c", is_active=True, page_sizes={},
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.run_command()
        self.assertFalse(PdfExtraction.objects.filter(record=self.record).exists())
        chunks.refresh_from_db()
        self.assertFalse(chunks.is_active, "Ask IRIS could still cite the flagged manuscript")

    def test_rdco_is_told_once_per_record(self):
        # Two uploaders' files on one record fail: each uploader is told, RDCO once.
        RecordFile.objects.create(record=self.record, filename="other.com", uploaded_by=self.rdco,
                                  file=ContentFile(EICAR, name="other.com"))
        with self.captureOnCommitCallbacks(execute=True):
            self.run_command()
        told = Notification.objects.filter(notif_type__name="File Quarantined")
        self.assertEqual(told.filter(broadcast_to_role__name="RDCO", record=self.record).count(), 1)
        self.assertTrue(told.filter(recipient=self.rdco).exists())

    def test_a_quarantined_file_answers_no_longer_available(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.run_command()
        self.client.force_authenticate(self.rdco)
        response = self.client.get(f"/api/v1/documents/files/{self.bad.pk}/download/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], FILE_GONE)
        self.assertEqual(self.client.get(f"/api/v1/documents/files/{self.good.pk}/download/").status_code, 200)

    def test_it_is_idempotent(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.run_command()
        self.assertIn("1 stored file(s): 1 clean, 0 quarantined", self.run_command())

    def test_a_scanner_that_is_down_stops_the_run_and_changes_nothing(self):
        with use_scanner(FakeScanner(down=True)), self.assertRaises(CommandError):
            self.run_command()
        self.bad.refresh_from_db()
        self.assertTrue(self.bad.file)
        self.assertEqual(list(Path(self.quarantine).iterdir()), [])
