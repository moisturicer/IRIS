"""Each Version keeps its review text, read on campus without AI (IR-871,
ADR-058 §1 as amended 2026-11-05). One class per acceptance criterion.

The sandbox is replaced by `in_process_sandbox`, the same reader in this
process, so these run on any platform; the sandbox itself is
`test_review_text_sandbox.py`'s, on Linux. A manuscript upload here is written
to the Record directly, as the upload endpoint would leave it, because the
endpoint's own PDF check is IR-830's and needs Linux.
"""
import hashlib
import uuid
from io import StringIO
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.documents.models import PdfExtraction
from apps.records.models import Record, RecordVersion, ReviewText, ReviewTextSection, ReviewTextState
from apps.records.review_text import store
from apps.records.review_text.testing import THESIS, blank, in_process_sandbox, pdf
from apps.records.versions import versions_payload
from apps.reviews.test_new_version import NewVersionTestBase
from core.enums import Party, PipelineStatus

V1 = pdf(THESIS)
V2_PAGES = [page[:] for page in THESIS]
V2_PAGES[1] = V2_PAGES[1][:-1] + [("para", ["This study asks whether two plants are feasible."])]
V2 = pdf(V2_PAGES)

SANDBOX = "apps.records.review_text.sandbox.read_in_sandbox"


def _file(data, name):
    return ContentFile(data, name=name)


def text_url(record, number):
    return reverse("record-version-text", args=[record.pk, number])


class ReviewTextTestBase(NewVersionTestBase):

    def thesis(self, *parties, body=V1):
        record = self.make_record(abstract_file=_file(body, "paper.pdf"))
        with patch("apps.records.tasks.read_review_text.delay"):
            from apps.reviews import routing
            routing.enter_at_adviser(record, self.owner)
        if parties:
            self.accepted_to(record, *parties)
        record.refresh_from_db()
        return record

    def owner_uploads(self, record, body):
        """What a revised manuscript's upload leaves on the Record (`manuscript_changes`)."""
        record.abstract_file.save("revised.pdf", ContentFile(body), save=False)
        record.manuscript_revision = uuid.uuid4()
        record.manuscript_sha256 = hashlib.sha256(body).hexdigest()
        record.manuscript_filename = "revised.pdf"
        record.save(update_fields=["abstract_file", "manuscript_revision", "manuscript_sha256",
                                   "manuscript_filename"])

    def resubmitted(self, record, body=None, title=None):
        """IERC asks; the owner uploads `body` and/or edits the title; submits v2."""
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        if body is not None:
            self.owner_uploads(record, body)
        if title is not None:
            self.edit_title(record, title)
        with patch("apps.records.tasks.read_review_text.delay"), \
                patch("apps.documents.tasks.extract_manuscript_text.delay"):
            self.submitted(record)
        return self.version(record, 2)

    def version(self, record, number):
        return RecordVersion.objects.select_related("review_text").get(record=record, number=number)

    def read_all(self, record):
        with patch(SANDBOX, side_effect=in_process_sandbox):
            for text in ReviewText.objects.filter(record=record):
                store.read_text(text.pk)

    def keys(self, text):
        return list(text.sections.values_list("key", flat=True))


class EachVersionHasItsOwnTextTests(ReviewTextTestBase):
    """After v2 is submitted, v1 and v2 each have their own review text, linked to their Version."""

    def test_submission_attaches_a_pending_text_and_queues_its_read_after_commit(self):
        record = self.make_record(abstract_file=_file(V1, "paper.pdf"))
        from apps.reviews import routing

        with patch("apps.records.tasks.read_review_text.delay") as queued, \
                self.captureOnCommitCallbacks(execute=True):
            routing.enter_at_adviser(record, self.owner)
        v1 = self.version(record, 1)
        self.assertEqual(v1.review_text.state, ReviewTextState.PENDING)
        self.assertEqual(v1.review_text.source_file, v1.manuscript.name)
        queued.assert_called_once_with(v1.review_text_id)

    def test_v1_and_v2_each_keep_their_own_text(self):
        record = self.thesis(Party.IERC)
        v2 = self.resubmitted(record, body=V2)
        self.read_all(record)
        v1, v2 = self.version(record, 1), self.version(record, 2)

        self.assertNotEqual(v1.review_text_id, v2.review_text_id)
        self.assertEqual(v2.review_text.source_file, v2.manuscript.name)
        for version in (v1, v2):
            self.assertEqual(version.review_text.state, ReviewTextState.READ)
            self.assertIn("statement of the problem", self.keys(version.review_text))
        changed = {
            v.number: v.review_text.sections.get(key="statement of the problem").passages[0]["text"]
            for v in (v1, v2)
        }
        self.assertEqual(changed, {
            1: "This study asks whether a plant is feasible.",
            2: "This study asks whether two plants are feasible.",
        })

    def test_the_reader_and_when_are_recorded(self):
        record = self.thesis()
        self.read_all(record)
        text = self.version(record, 1).review_text
        self.assertTrue(text.reader.startswith("review-reader-1/pdfplumber-"))
        self.assertIsNotNone(text.read_at)
        self.assertEqual(text.page_count, 3)
        self.assertFalse(text.read_after_submission)


class NoGateNoNetworkTests(ReviewTextTestBase):
    """It is read with no network call and no model, and the extraction gate never refuses it."""

    def test_an_embargoed_paper_without_ai_consent_is_read_and_the_gate_is_never_asked(self):
        record = self.thesis()
        self.assertTrue(Record.objects.get(pk=record.pk).is_embargoed)   # every paper starts so (IR-882)
        extractions = PdfExtraction.objects.filter(record=record).count()

        with patch("apps.ai.extraction.gate.awaits_disclosure",
                   side_effect=AssertionError("review text asked the extraction gate")), \
                patch("apps.documents.sources.awaits_disclosure",
                      side_effect=AssertionError("review text asked the extraction gate")):
            self.read_all(record)

        self.assertEqual(self.version(record, 1).review_text.state, ReviewTextState.READ)
        # Reading review text makes no Extraction and no chunks for the AI.
        self.assertEqual(PdfExtraction.objects.filter(record=record).count(), extractions)
        from apps.ai.models import ChunkSet
        self.assertFalse(ChunkSet.objects.filter(record=record).exists())

    def test_the_read_opens_no_socket(self):
        record = self.thesis()
        import socket

        def refuse(*args, **kwargs):
            raise AssertionError("review text opened a socket")

        with patch.object(socket.socket, "connect", refuse), \
                patch.object(socket, "create_connection", refuse):
            self.read_all(record)
        self.assertEqual(self.version(record, 1).review_text.state, ReviewTextState.READ)


class MetadataOnlyVersionTests(ReviewTextTestBase):
    """A metadata-only Version reads nothing again and shares the previous text."""

    def test_a_title_only_version_shares_v1s_text_and_queues_no_read(self):
        record = self.thesis(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.edit_title(record, "A revised title")
        with patch("apps.records.tasks.read_review_text.delay") as queued, \
                patch("apps.documents.tasks.extract_manuscript_text.delay"), \
                self.captureOnCommitCallbacks(execute=True):
            self.submitted(record)

        v1, v2 = self.version(record, 1), self.version(record, 2)
        self.assertEqual(v2.review_text_id, v1.review_text_id)
        queued.assert_not_called()
        self.assertEqual(ReviewText.objects.filter(record=record).count(), 1)

    def test_a_version_with_no_manuscript_has_no_text(self):
        record = self.make_record()
        from apps.reviews import routing
        routing.enter_at_adviser(record, self.owner)
        self.assertIsNone(self.version(record, 1).review_text)
        self.assertIsNone(versions_payload(record)[0]["review_text"])


class WithdrawingARevisionTests(ReviewTextTestBase):
    """Withdrawing a revision deletes only the unsubmitted upload's text, never a Version's."""

    def test_withdrawing_the_last_request_keeps_every_versions_text(self):
        record = self.thesis(Party.IERC)
        self.read_all(record)
        self.opened_seat(record, Party.IERC, self.ierc)
        request = self.asked(record, self.ierc)
        self.owner_uploads(record, V2)   # never submitted, so never read
        before = list(ReviewText.objects.filter(record=record).values_list("pk", "state"))
        sections = ReviewTextSection.objects.filter(text__record=record).count()

        response = self.withdraw(record, self.ierc, request.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        self.assertEqual(record.abstract_file.name, self.version(record, 1).manuscript.name)
        self.assertEqual(list(ReviewText.objects.filter(record=record).values_list("pk", "state")), before)
        self.assertEqual(ReviewTextSection.objects.filter(text__record=record).count(), sections)

    def test_an_unsubmitted_upload_is_never_read(self):
        record = self.thesis(Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.owner_uploads(record, V2)
        self.assertFalse(ReviewText.objects.filter(source_file=record.abstract_file.name).exists())

    def test_no_code_can_delete_a_text_a_version_names(self):
        from django.db.models import RestrictedError

        record = self.thesis()
        with self.assertRaises(RestrictedError):
            self.version(record, 1).review_text.delete()


class KeptForTheRecordsLifeTests(ReviewTextTestBase):
    """Kept for the Record's life, whether published, unlisted or rejected."""

    def test_the_text_outlasts_every_ending_and_a_soft_delete(self):
        record = self.thesis()
        self.read_all(record)
        text = self.version(record, 1).review_text
        for ending in (PipelineStatus.PUBLISHED, PipelineStatus.COMPLETED, PipelineStatus.REJECTED):
            Record.objects.filter(pk=record.pk).update(pipeline_status=ending)
            self.assertTrue(ReviewTextSection.objects.filter(text=text).exists(), ending)
        Record.objects.filter(pk=record.pk).update(is_deleted=True)
        self.assertEqual(ReviewText.objects.get(pk=text.pk).state, ReviewTextState.READ)


class NoTextTests(ReviewTextTestBase):
    """A scanned or unreadable PDF stores "No text for vN", never empty text."""

    def test_a_scan_stores_no_text_and_says_so(self):
        record = self.thesis(body=blank(pages=2))
        self.read_all(record)
        text = self.version(record, 1).review_text
        self.assertEqual((text.state, text.reason), (ReviewTextState.NO_TEXT, "no_text_layer"))
        self.assertFalse(text.sections.exists())
        self.assertEqual(versions_payload(record)[0]["review_text"]["message"],
                         "No text for v1, so it can't be compared.")

    def test_an_unreadable_file_stores_no_text(self):
        record = self.thesis(body=b"%PDF-1.7 not a real document")
        self.read_all(record)
        text = self.version(record, 1).review_text
        self.assertEqual((text.state, text.reason), (ReviewTextState.NO_TEXT, "unreadable"))

    def test_without_sandbox_limits_nothing_is_read_and_the_text_waits(self):
        record = self.thesis()
        with override_settings(REVIEW_TEXT_WALL_SECONDS=None):
            store.read_text(self.version(record, 1).review_text_id)
        text = self.version(record, 1).review_text
        self.assertEqual((text.state, text.reason), (ReviewTextState.UNAVAILABLE, "limits_unset"))
        self.assertEqual(versions_payload(record)[0]["review_text"]["message"],
                         "v1's text hasn't been read yet.")

    def test_a_file_missing_at_submission_is_no_text_not_text_not_kept(self):
        # "Text not kept" is for Versions from before IR-871 (ADR-058 §1 point 4).
        record = self.thesis()
        text = self.version(record, 1).review_text
        ReviewText.objects.filter(pk=text.pk).update(source_file="manuscripts/gone.pdf")
        store.read_text(text.pk)
        text.refresh_from_db()
        self.assertEqual((text.state, text.reason), (ReviewTextState.NO_TEXT, "file_missing"))

    def test_bytes_that_are_not_the_submitted_file_store_nothing(self):
        record = self.thesis()
        text = self.version(record, 1).review_text
        ReviewText.objects.filter(pk=text.pk).update(manuscript_sha256="0" * 64)
        with patch(SANDBOX, side_effect=in_process_sandbox):
            store.read_text(text.pk)
        text.refresh_from_db()
        self.assertEqual((text.state, text.reason), (ReviewTextState.NO_TEXT, "file_changed"))
        self.assertFalse(text.sections.exists())

    def test_output_of_the_wrong_shape_is_no_text_and_never_retried(self):
        from apps.records.review_text import sandbox

        record = self.thesis()
        text = self.version(record, 1).review_text
        with patch(SANDBOX, return_value=sandbox.outcome_of({"reader": "x"})):
            store.read_text(text.pk)
        text.refresh_from_db()
        self.assertEqual((text.state, text.reason), (ReviewTextState.NO_TEXT, "invalid_output"))
        self.assertEqual(store.backfill_plan(record.pk), [])


class NeverReReadInPlaceTests(ReviewTextTestBase):
    """Stored text records its reader and is never re-read in place (ADR-058 §1 point 5)."""

    def test_a_second_read_changes_nothing(self):
        record = self.thesis()
        self.read_all(record)
        text = self.version(record, 1).review_text
        sections = list(text.sections.values_list("pk", "text_hash"))

        with patch(SANDBOX, side_effect=AssertionError("re-read in place")):
            self.assertEqual(store.read_text(text.pk), ReviewTextState.READ)
        text.refresh_from_db()
        self.assertEqual(list(text.sections.values_list("pk", "text_hash")), sections)

    def test_a_read_finished_by_another_worker_is_not_overwritten(self):
        record = self.thesis()
        text = self.version(record, 1).review_text
        self.read_all(record)
        from apps.records.review_text import sandbox

        self.assertEqual(store._write(text.pk, sandbox.Outcome(sandbox.NO_TEXT, "unreadable")),
                         ReviewTextState.READ)


class EarlierVersionsTests(ReviewTextTestBase):
    """Versions from before this change are read from their own file, otherwise "text not kept"."""

    def before_ir_871(self, record):
        """What every Version written before IR-871 has: no review text."""
        RecordVersion.objects.filter(record=record).update(review_text=None)
        ReviewText.objects.filter(record=record).delete()

    def test_the_command_reads_each_version_from_its_own_file_and_shares_metadata_only_ones(self):
        record = self.thesis(Party.IERC)
        self.resubmitted(record, title="A new title")
        self.before_ir_871(record)

        with patch(SANDBOX, side_effect=in_process_sandbox), \
                patch("sys.platform", "linux"):
            call_command("read_review_texts", stdout=StringIO())

        v1, v2 = self.version(record, 1), self.version(record, 2)
        self.assertEqual(v1.review_text.state, ReviewTextState.READ)
        self.assertTrue(v1.review_text.read_after_submission)
        self.assertEqual(v1.review_text.source_file, v1.manuscript.name)
        self.assertEqual(v2.review_text_id, v1.review_text_id)

    def test_a_version_whose_file_is_gone_reads_text_not_kept(self):
        record = self.thesis()
        self.before_ir_871(record)
        with patch.object(default_storage, "exists", return_value=False):
            call_command("read_review_texts", stdout=StringIO())
        v1 = self.version(record, 1)
        self.assertEqual(v1.review_text.state, ReviewTextState.NOT_KEPT)
        self.assertEqual(versions_payload(record)[0]["review_text"]["message"], "v1's text was not kept.")

    def test_dry_run_writes_nothing_and_a_second_run_finds_nothing(self):
        record = self.thesis()
        self.before_ir_871(record)
        out = StringIO()
        call_command("read_review_texts", "--dry-run", stdout=out)
        self.assertIn(f"record {record.pk} v1: read", out.getvalue())
        self.assertFalse(ReviewText.objects.filter(record=record).exists())

        with patch(SANDBOX, side_effect=in_process_sandbox), patch("sys.platform", "linux"):
            call_command("read_review_texts", stdout=StringIO())
        self.assertEqual(store.backfill_plan(record.pk), [])

    def test_it_refuses_to_read_without_the_sandbox_limits(self):
        record = self.thesis()
        self.before_ir_871(record)
        with override_settings(REVIEW_TEXT_MEMORY_MIB=None), self.assertRaises(CommandError):
            call_command("read_review_texts", stdout=StringIO())
        self.assertFalse(ReviewText.objects.filter(record=record).exists())

    def test_it_retries_a_text_left_unavailable(self):
        record = self.thesis()
        with override_settings(REVIEW_TEXT_WALL_SECONDS=None):
            store.read_text(self.version(record, 1).review_text_id)
        with patch(SANDBOX, side_effect=in_process_sandbox), patch("sys.platform", "linux"):
            call_command("read_review_texts", stdout=StringIO())
        self.assertEqual(self.version(record, 1).review_text.state, ReviewTextState.READ)

    def test_it_retries_a_text_whose_queued_read_was_lost_but_not_one_in_flight(self):
        from datetime import timedelta

        from django.utils import timezone

        record = self.thesis()
        text = self.version(record, 1).review_text
        self.assertEqual(store.backfill_plan(record.pk), [])   # just queued: in flight
        ReviewText.objects.filter(pk=text.pk).update(
            created_at=timezone.now() - store.STALE_PENDING - timedelta(minutes=1),
        )
        self.assertEqual([a for _, a, _ in store.backfill_plan(record.pk)], ["retry"])
        with patch(SANDBOX, side_effect=in_process_sandbox), patch("sys.platform", "linux"):
            call_command("read_review_texts", stdout=StringIO())
        self.assertEqual(self.version(record, 1).review_text.state, ReviewTextState.READ)

    def test_a_metadata_only_version_shares_across_a_gap_in_numbers(self):
        record = self.thesis(Party.IERC)
        self.resubmitted(record, title="A new title")
        self.before_ir_871(record)
        RecordVersion.objects.filter(record=record, number=2).update(number=5)

        with patch(SANDBOX, side_effect=in_process_sandbox), patch("sys.platform", "linux"):
            call_command("read_review_texts", stdout=StringIO())
        v1, v5 = self.version(record, 1), self.version(record, 5)
        self.assertEqual(v5.review_text_id, v1.review_text_id)


class ServedOnlyUnderMayReadReviewTests(ReviewTextTestBase):
    """Review text is served only under `may_read_review` (ADR-058 §4)."""

    def test_a_participant_reads_the_sections_and_the_read_is_audited(self):
        record = self.thesis()
        self.read_all(record)
        self.client.force_authenticate(self.adviser)
        response = self.client.get(text_url(record, 1))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], ReviewTextState.READ)
        self.assertEqual(response.data["version"], 1)
        section = next(s for s in response.data["sections"] if s["key"] == "statement of the problem")
        self.assertEqual(section["passages"][0]["text"], "This study asks whether a plant is feasible.")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(AuditEvent.objects.filter(
            record=record, user=self.adviser, metadata__source="review_text",
        ).exists())

    def test_anyone_else_gets_the_404_a_missing_version_gets(self):
        record = self.thesis()
        self.read_all(record)
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)
        self.client.force_authenticate(self.stranger)   # reads the published Record, not its review
        missing = self.client.get(text_url(record, 99))
        refused = self.client.get(text_url(record, 1))
        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(refused.data, missing.data)

    def test_a_text_not_read_yet_answers_with_its_state_and_no_sections(self):
        record = self.thesis()
        self.client.force_authenticate(self.owner)
        response = self.client.get(text_url(record, 1))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.data["state"], response.data["sections"]), ("pending", []))
        self.assertEqual(response.data["message"], "v1's text is being read.")

    def test_the_version_payload_reports_each_texts_state(self):
        record = self.thesis()
        self.read_all(record)
        entry = versions_payload(record)[0]["review_text"]
        self.assertEqual(entry["state"], ReviewTextState.READ)
        self.assertIsNone(entry["message"])
        self.assertEqual(entry["url"], f"/api/v1/records/{record.pk}/versions/1/text/")


class RealSandboxTests(ReviewTextTestBase):
    """The worker's read through the real IR-830 subprocess, end to end. Linux only, so CI."""

    def setUp(self):
        super().setUp()
        import sys
        if sys.platform != "linux":
            self.skipTest("the sandbox needs Linux RLIMIT_AS")

    def test_the_task_reads_v1_in_the_sandbox(self):
        from apps.records.tasks import read_review_text

        record = self.thesis()
        self.assertEqual(read_review_text(self.version(record, 1).review_text_id), ReviewTextState.READ)
        text = self.version(record, 1).review_text
        self.assertIn("statement of the problem", self.keys(text))
