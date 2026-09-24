"""Bulk-loading a corpus of PDFs from a directory (IR-313).

The load-bearing behaviour here is the catch the command exists to handle:
writing `abstract_file` through the ORM reaches none of
`RecordViewSet._queue_manuscript_extraction_if_present`'s hook, so the
command has to create the `PdfExtraction` row and queue
`extract_manuscript_text` itself. `test_it_queues_manuscript_extraction`
and `test_it_creates_the_manuscript_extraction_row` are the tests that would
fail first if that logic were ever dropped.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import User
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.management.commands.load_corpus import DEFAULT_OWNER_EMAIL
from apps.records.models import Classification, Record, RecordOwner, RecordType
from core.enums import PipelineStatus

FAKE_PDF = b"%PDF-1.7 fake bytes"


def _write(root: Path, category: str, filename: str, content: bytes = FAKE_PDF) -> Path:
    folder = root / category
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_bytes(content)
    return path


class _LoadsCorpus(TestCase):
    """Shared load() helper: runs the command with its narration swallowed
    and its on_commit-queued extraction captured rather than actually sent
    to Celery.

    `force=True` by default -- Django forces `DEBUG = False` in tests, so
    the production guard fires on every call unless overridden. The guard
    is exercised deliberately in `LoadCorpusGuardTests` rather than tripped
    over here.
    """

    def load(self, directory, **kwargs):
        kwargs.setdefault("force", True)
        with patch("apps.documents.tasks.extract_manuscript_text.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                call_command("load_corpus", directory, stdout=StringIO(), **kwargs)
        return mock_delay


class LoadCorpusTests(_LoadsCorpus):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_it_creates_one_record_per_pdf(self):
        _write(self.root, "active learning", "Paper One.pdf")
        _write(self.root, "active learning", "Paper Two.pdf")

        self.load(str(self.root))

        self.assertEqual(Record.objects.count(), 2)
        titles = set(Record.objects.values_list("title", flat=True))
        self.assertEqual(titles, {"Paper One", "Paper Two"})

    def test_the_pdf_is_attached_as_the_manuscript(self):
        _write(self.root, "econometrics", "Paper.pdf")

        self.load(str(self.root))

        record = Record.objects.get(title="Paper")
        self.assertTrue(record.abstract_file)
        self.assertEqual(record.abstract_file.read(), FAKE_PDF)

    def test_a_folder_becomes_a_classification(self):
        _write(self.root, "hardware-architecture", "Paper.pdf")

        self.load(str(self.root))

        self.assertTrue(Classification.objects.filter(name="hardware-architecture").exists())
        record = Record.objects.get(title="Paper")
        self.assertEqual(record.classification.name, "hardware-architecture")

    def test_an_existing_classification_is_reused_not_duplicated(self):
        Classification.objects.create(name="econometrics")
        _write(self.root, "econometrics", "Paper.pdf")

        self.load(str(self.root))

        self.assertEqual(Classification.objects.filter(name="econometrics").count(), 1)

    def test_defaults_to_thesis_research_and_a_publicly_visible_status(self):
        _write(self.root, "econometrics", "Paper.pdf")

        self.load(str(self.root))

        record = Record.objects.get(title="Paper")
        self.assertEqual(record.record_type.name, "Thesis / Research")
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)

    def test_record_type_and_status_are_overridable(self):
        _write(self.root, "econometrics", "Paper.pdf")

        self.load(str(self.root), record_type="Project", status=PipelineStatus.DRAFT)

        record = Record.objects.get(title="Paper")
        self.assertEqual(record.record_type.name, "Project")
        self.assertEqual(record.pipeline_status, PipelineStatus.DRAFT)

    def test_an_owner_is_resolved_and_recorded_as_added_by_and_primary_owner(self):
        _write(self.root, "econometrics", "Paper.pdf")

        self.load(str(self.root))

        record = Record.objects.get(title="Paper")
        owner = User.objects.get(email=DEFAULT_OWNER_EMAIL)
        self.assertEqual(record.added_by, owner)
        ownership = RecordOwner.objects.get(record=record)
        self.assertEqual(ownership.user, owner)
        self.assertTrue(ownership.is_primary)
        self.assertFalse(owner.has_usable_password())

    def test_owner_email_is_overridable(self):
        _write(self.root, "econometrics", "Paper.pdf")

        self.load(str(self.root), owner_email="someone@cit.edu")

        record = Record.objects.get(title="Paper")
        self.assertEqual(record.added_by.email, "someone@cit.edu")

    def test_it_creates_the_manuscript_extraction_row(self):
        """The catch this command exists for: an ORM write reaches none of
        the viewset's `_queue_manuscript_extraction_if_present` hook."""
        _write(self.root, "econometrics", "Paper.pdf")

        self.load(str(self.root))

        record = Record.objects.get(title="Paper")
        extraction = PdfExtraction.objects.get(record=record)
        self.assertEqual(extraction.kind, DocumentKind.MANUSCRIPT)
        self.assertEqual(extraction.status, "queued")

    def test_it_queues_manuscript_extraction(self):
        _write(self.root, "econometrics", "Paper.pdf")

        mock_delay = self.load(str(self.root))

        record = Record.objects.get(title="Paper")
        mock_delay.assert_called_once_with(record.id)

    def test_a_non_pdf_file_is_skipped_not_fatal(self):
        _write(self.root, "econometrics", "Paper.pdf")
        _write(self.root, "econometrics", "notes.txt", content=b"not a pdf")

        self.load(str(self.root))

        self.assertEqual(Record.objects.count(), 1)

    def test_rerunning_does_not_duplicate_records(self):
        _write(self.root, "econometrics", "Paper.pdf")
        self.load(str(self.root))

        self.load(str(self.root))

        self.assertEqual(Record.objects.count(), 1)

    def test_rerunning_does_not_requeue_an_existing_record(self):
        _write(self.root, "econometrics", "Paper.pdf")
        self.load(str(self.root))

        mock_delay = self.load(str(self.root))

        mock_delay.assert_not_called()

    def test_the_same_title_in_two_categories_is_not_a_duplicate(self):
        """Idempotency is scoped to (title, classification) -- the same
        paper filed under two categories is two distinct Records, not one
        the second folder's copy is silently skipped for."""
        _write(self.root, "econometrics", "Paper.pdf")
        _write(self.root, "active learning", "Paper.pdf")

        self.load(str(self.root))

        self.assertEqual(Record.objects.filter(title="Paper").count(), 2)

    def test_dry_run_against_an_already_loaded_corpus_reports_no_new_records(self):
        """A dry-run's idempotency check has to see the real Classification,
        not stand in a `None` for it -- otherwise every already-loaded
        record compares against the wrong classification and reads as new
        on every subsequent dry-run, which is exactly when the preview is
        supposed to be trustworthy."""
        _write(self.root, "econometrics", "Paper.pdf")
        self.load(str(self.root))

        out = StringIO()
        with patch("apps.documents.tasks.extract_manuscript_text.delay") as mock_delay:
            call_command("load_corpus", str(self.root), force=True, dry_run=True, stdout=out)

        self.assertIn("already exists", out.getvalue())
        self.assertIn("Would create 0 record(s)", out.getvalue())
        mock_delay.assert_not_called()

    def test_dry_run_writes_nothing(self):
        _write(self.root, "econometrics", "Paper.pdf")
        # RecordType is pre-seeded by a data migration (records/0002), so the
        # count to compare against is whatever it already is, not zero.
        record_types_before = RecordType.objects.count()

        mock_delay = self.load(str(self.root), dry_run=True)

        self.assertEqual(Record.objects.count(), 0)
        self.assertEqual(Classification.objects.count(), 0)
        self.assertEqual(RecordType.objects.count(), record_types_before)
        mock_delay.assert_not_called()

    def test_the_summary_reports_created_skipped_and_non_pdf_counts(self):
        _write(self.root, "econometrics", "Paper.pdf")
        _write(self.root, "econometrics", "notes.txt", content=b"not a pdf")
        out = StringIO()

        with patch("apps.documents.tasks.extract_manuscript_text.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                call_command("load_corpus", str(self.root), force=True, stdout=out)

        report = out.getvalue()
        self.assertIn("Created 1 record(s)", report)
        self.assertIn("1 non-PDF file(s) skipped", report)
        self.assertIn("1 extraction(s) queued", report)

    def test_a_missing_directory_is_a_command_error(self):
        with self.assertRaises(CommandError):
            call_command("load_corpus", str(self.root / "does-not-exist"), force=True, stdout=StringIO())

    def test_an_empty_directory_reports_no_categories_and_writes_nothing(self):
        self.load(str(self.root))

        self.assertEqual(Record.objects.count(), 0)


class LoadCorpusGuardTests(_LoadsCorpus):
    """The refusal that keeps a stray run off a production database."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _write(self.root, "econometrics", "Paper.pdf")

    def test_it_refuses_to_run_with_debug_off(self):
        # No `override_settings(DEBUG=False)`: the test runner already forces
        # it off, and writing it here would suggest this test sets up a
        # condition it merely inherits.
        with self.assertRaises(CommandError):
            call_command("load_corpus", str(self.root), stdout=StringIO())
        self.assertEqual(Record.objects.count(), 0)

    def test_the_refusal_names_the_way_past_it(self):
        with self.assertRaises(CommandError) as caught:
            call_command("load_corpus", str(self.root), stdout=StringIO())
        self.assertIn("--force", str(caught.exception))

    def test_force_overrides_the_refusal(self):
        self.load(str(self.root))

        self.assertEqual(Record.objects.count(), 1)
