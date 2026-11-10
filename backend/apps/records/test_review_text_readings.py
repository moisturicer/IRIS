"""Both sides of a comparison are read by one reader (IR-873, ADR-058 §3 as
amended 2026-11-08), and `GET /records/<id>/versions/compare/` serves it.

A reader change is simulated by patching `reader.reader_version`, which both
names the reader the comparison asks for and is what the reader stamps on a
reading. The reader itself runs in this process (`in_process_sandbox`).
"""
import json
from contextlib import contextmanager
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status

from apps.audit.models import AuditEvent
from apps.records.models import Record, ReviewText, ReviewTextState
from apps.records.review_text import deployed_reader, reader, readings, sandbox
from apps.records.review_text.testing import blank, in_process_sandbox
from apps.records.test_review_text import SANDBOX, V2, ReviewTextTestBase
from apps.reviews.models import ReviewComment, ReviewRound
from core.enums import Party, PipelineStatus, ReviewVerdict

NEXT_READER = "review-reader-99/pdfplumber-test"
QUEUE = "apps.records.tasks.read_review_text.delay"


@contextmanager
def next_reader():
    """Deploy a newer reader: what the comparison asks for, and what reads."""
    with patch("apps.records.review_text.deployed_reader.reader_version", return_value=NEXT_READER), \
            patch("apps.records.review_text.reader.reader_version", return_value=NEXT_READER):
        yield


def test_the_web_side_names_the_reader_exactly_as_the_reader_does():
    # `deployed_reader.py` repeats the reader's name because the reader is never
    # imported outside the sandbox. Raise RULES_VERSION in both together.
    assert deployed_reader.RULES_VERSION == reader.RULES_VERSION
    assert deployed_reader.reader_version() == reader.reader_version()


def failing_sandbox(source):
    return sandbox.Outcome(sandbox.UNAVAILABLE, "timeout")


def compare_url(record):
    return reverse("record-version-compare", args=[record.pk])


class ComparisonTestBase(ReviewTextTestBase):

    def two_versions(self, *, read=True):
        record = self.thesis(Party.IERC)
        self.resubmitted(record, body=V2)
        if read:
            self.read_all(record)
        return record, self.version(record, 1), self.version(record, 2)

    def read_pending(self, record, sandbox_fn=in_process_sandbox):
        with patch(SANDBOX, side_effect=sandbox_fn):
            for text in ReviewText.objects.filter(record=record, state=ReviewTextState.PENDING):
                from apps.records.review_text import store
                store.read_text(text.pk)

    def pair(self, record):
        return readings.pair(self.version(record, 1), self.version(record, 2))


class SameReaderTests(ComparisonTestBase):
    """Two readings by different readers are never compared."""

    def test_versions_read_by_the_current_reader_are_compared_as_they_are(self):
        record, v1, v2 = self.two_versions()
        found = self.pair(record)
        self.assertEqual(found.state, readings.READY)
        self.assertEqual((found.old.pk, found.new.pk), (v1.review_text_id, v2.review_text_id))
        self.assertEqual(ReviewText.objects.filter(record=record).count(), 2)

    def test_a_newer_reader_reads_both_again_beside_their_originals(self):
        record, v1, v2 = self.two_versions()
        originals = {t.pk: (t.reader, self.keys(t)) for t in ReviewText.objects.filter(record=record)}
        with next_reader():
            with patch(QUEUE):
                self.assertEqual(self.pair(record).state, readings.PREPARING)
            self.read_pending(record)
            with patch(QUEUE):
                found = self.pair(record)

        self.assertEqual(found.state, readings.READY)
        self.assertEqual(found.old.reader, NEXT_READER)
        self.assertEqual(found.new.reader, NEXT_READER)
        self.assertNotIn(found.old.pk, originals)
        # Each Version still points at its original, which is unchanged.
        self.assertEqual(self.version(record, 1).review_text_id, v1.review_text_id)
        self.assertEqual(self.version(record, 2).review_text_id, v2.review_text_id)
        for text in ReviewText.objects.filter(pk__in=originals):
            self.assertEqual((text.reader, self.keys(text)), originals[text.pk])

    def test_asking_again_finds_the_reading_already_asked_for(self):
        record, _, _ = self.two_versions()
        with next_reader(), patch(QUEUE):
            self.pair(record)
            self.pair(record)
        self.assertEqual(ReviewText.objects.filter(record=record).count(), 4)

    def test_if_the_newer_reader_fails_the_reader_both_share_is_used(self):
        record, v1, v2 = self.two_versions()
        with next_reader():
            with patch(QUEUE):
                self.pair(record)
            self.read_pending(record, failing_sandbox)
            with patch(QUEUE):
                found = self.pair(record)
        self.assertEqual(found.state, readings.READY)
        self.assertEqual((found.old.pk, found.new.pk), (v1.review_text_id, v2.review_text_id))

    def test_with_no_reader_shared_a_failure_is_unavailable_and_retried_next_time(self):
        record = self.thesis(Party.IERC)
        self.read_all(record)                                  # v1 by today's reader
        with next_reader():
            self.resubmitted(record, body=V2)                  # v2 after the upgrade
            self.read_pending(record)
            with patch(QUEUE):
                self.pair(record)                              # asks for v1 by the new reader
            self.read_pending(record, failing_sandbox)
            with patch(QUEUE) as queued, self.captureOnCommitCallbacks(execute=True):
                found = self.pair(record)
        self.assertEqual(found.state, readings.UNAVAILABLE)
        retried = ReviewText.objects.get(record=record, requested_reader=NEXT_READER,
                                         state=ReviewTextState.UNAVAILABLE)
        queued.assert_called_once_with(retried.pk)

    def test_submitting_a_version_queues_the_same_reader_for_earlier_ones(self):
        record = self.thesis(Party.IERC)
        self.read_all(record)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.owner_uploads(record, V2)
        with next_reader(), patch(QUEUE) as queued, \
                patch("apps.documents.tasks.extract_manuscript_text.delay"), \
                self.captureOnCommitCallbacks(execute=True):
            self.submitted(record)
        v2 = self.version(record, 2)
        added = ReviewText.objects.get(record=record, requested_reader=NEXT_READER,
                                       source_file=self.version(record, 1).manuscript.name)
        self.assertEqual(v2.review_text.requested_reader, NEXT_READER)
        self.assertCountEqual([c.args[0] for c in queued.call_args_list], [v2.review_text_id, added.pk])

    def test_a_text_still_being_read_when_the_reader_changes_is_preparing_not_no_text(self):
        record, v1, v2 = self.two_versions(read=False)       # asked for under today's reader
        with next_reader():
            with patch(QUEUE):
                self.assertEqual(self.pair(record).state, readings.PREPARING)
            self.read_pending(record)                        # the newer reader reads them
            with patch(QUEUE):
                found = self.pair(record)
        self.assertEqual(found.state, readings.READY)
        self.assertEqual((found.old.pk, found.new.pk), (v1.review_text_id, v2.review_text_id))
        self.assertEqual(found.old.reader, NEXT_READER)
        self.assertEqual(ReviewText.objects.filter(record=record).count(), 2)

    def test_a_read_that_failed_before_the_reader_changed_is_retried(self):
        record, v1, v2 = self.two_versions(read=False)
        self.read_pending(record, failing_sandbox)           # failed under today's reader
        with next_reader(), patch(QUEUE) as queued, self.captureOnCommitCallbacks(execute=True):
            found = self.pair(record)
        self.assertEqual(found.state, readings.UNAVAILABLE)
        self.assertCountEqual([c.args[0] for c in queued.call_args_list],
                              [v1.review_text_id, v2.review_text_id])
        self.assertEqual(ReviewText.objects.filter(record=record).count(), 2)

    def test_a_version_with_no_text_is_no_text_whatever_the_reader(self):
        record = self.thesis(Party.IERC, body=blank())
        self.read_all(record)
        self.resubmitted(record, body=V2)
        self.read_all(record)
        with next_reader(), patch(QUEUE):
            found = self.pair(record)
        self.assertEqual(found.state, readings.NO_TEXT)
        self.assertEqual(found.without_text.number, 1)
        self.assertEqual(ReviewText.objects.filter(record=record).count(), 2)


class CompareEndpointTests(ComparisonTestBase):

    def get(self, record, user=None, **params):
        self.client.force_authenticate(user or self.owner)
        with patch(QUEUE):
            return self.client.get(compare_url(record), params)

    def test_it_serves_the_changes_between_two_versions(self):
        record, _, _ = self.two_versions()
        response = self.get(record)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        body = response.data
        self.assertEqual((body["state"], body["from"], body["to"]), ("ready", 1, 2))
        self.assertEqual(body["counts"]["changed"], 1)
        [section] = [s for s in body["sections"] if s["status"] == "changed"]
        self.assertEqual(section["to"]["key"], "statement of the problem")
        self.assertIn("comparison_version", body)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(AuditEvent.objects.filter(
            record=record, user=self.owner, metadata__source="version_comparison",
        ).exists())

    def test_no_response_names_a_reader(self):
        record, _, _ = self.two_versions()
        self.client.force_authenticate(self.owner)
        text = self.client.get(reverse("record-version-text", args=[record.pk, 1]))
        self.assertNotIn("reader", text.data)
        with next_reader():
            preparing = self.get(record)
        self.assertEqual(preparing.data["state"], "preparing")
        self.assertEqual(preparing.data["message"], "Preparing the comparison…")
        for response in (text, self.get(record), preparing):
            self.assertNotIn("review-reader", json.dumps(response.data, default=str))

    def test_a_version_with_no_text_says_so(self):
        record = self.thesis(Party.IERC, body=blank())
        self.read_all(record)
        self.resubmitted(record, body=V2)
        self.read_all(record)
        body = self.get(record).data
        self.assertEqual(body["state"], "no_text")
        self.assertEqual(body["message"], "No text for v1, so it can't be compared.")

    def test_the_default_pair_starts_at_the_version_this_reviewer_last_finished(self):
        record, _, _ = self.two_versions()
        self.asked(record, self.ierc)
        self.owner_uploads(record, b"%PDF-1.4 v3")
        with patch(QUEUE), patch("apps.documents.tasks.extract_manuscript_text.delay"):
            self.submitted(record)
        self.assertEqual(self.get(record, self.ierc).data["from"], 2)   # previous -> latest
        ReviewRound.objects.create(record=record, actor=self.ierc, party=Party.IERC,
                                   version=self.version(record, 1),
                                   verdict=ReviewVerdict.COMMENT_ONLY)
        body = self.get(record, self.ierc).data
        self.assertEqual((body["from"], body["to"]), (1, 3))
        self.assertEqual(self.get(record, self.ierc, **{"from": 3, "to": 2}).data["from"], 2)

    def test_sent_threads_on_either_version_are_listed_under_their_section(self):
        record, v1, v2 = self.two_versions()

        def thread(version, page, quote, **extra):
            return ReviewComment.objects.create(
                record=record, author=self.ierc, body="Why?", party=Party.IERC, version=version,
                anchor_version=version, anchor_page=page, anchor_quote=quote, **extra).pk

        background = thread(v1, 2, "Metro Cebu generates about 2,000 tonnes")
        problem = thread(v2, 2, "two plants are feasible")
        by_page = thread(v1, 3, "words no reading has")       # falls back to its page
        thread(v1, 2, "Metro Cebu", is_draft=True)            # a draft is nobody else's yet
        body = self.get(record).data
        keys = {i: (s["from"] or s["to"])["key"] for i, s in enumerate(body["sections"])}
        placed = {t["thread"]: (t["side"], keys.get(t["section"])) for t in body["threads"]}
        self.assertEqual(placed, {
            background: ("from", "background of the study"),
            problem: ("to", "statement of the problem"),
            by_page: ("from", "review of related literature"),
        })

    def test_a_pair_that_cant_be_compared_is_refused_saying_why(self):
        record = self.thesis(Party.IERC)
        one = self.get(record)
        self.assertEqual(one.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("one Version", one.data["detail"])
        record, _, _ = self.two_versions()
        for params in ({"from": "x", "to": 2}, {"from": 1}, {"from": 1, "to": 1},
                       {"from": 1, "to": 9}):
            self.assertEqual(self.get(record, **params).status_code, status.HTTP_400_BAD_REQUEST,
                             params)

    def test_anyone_the_review_refuses_gets_a_404(self):
        record, _, _ = self.two_versions()
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)
        refused = self.get(record, self.stranger)
        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(AuditEvent.objects.filter(
            record=record, user=self.stranger, metadata__source="version_comparison",
        ).exists())
