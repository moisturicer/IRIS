"""Each later Version finds an anchored thread's passage again (ADR-032 §7,
*Outdated threads*; IR-876). The papers are the IR-873 pair: v2 rewrites
"a plant is feasible" as "two plants are feasible" and changes nothing else.
The reader runs in this process (`in_process_sandbox`)."""
from unittest.mock import patch

from apps.records.review_text.testing import pdf
from apps.records.test_review_text import V2, V2_PAGES, ReviewTextTestBase
from apps.reviews import thread_places
from apps.reviews.models import ReviewComment
from core.enums import Party, ThreadPlaceOutcome, ThreadState

UNTOUCHED = "Metro Cebu generates about 2,000 tonnes"
EDITED = "a plant is feasible"

# v3 keeps v2's rewritten sentence and drops the literature paragraph.
V3_PAGES = [page[:] for page in V2_PAGES]
V3_PAGES[2] = [item for item in V3_PAGES[2] if "Davao" not in str(item)]
V3 = pdf(V3_PAGES)


class ThreadPlaceTestBase(ReviewTextTestBase):

    def two_versions(self, *, read=True):
        record = self.thesis(Party.IERC)
        v1 = self.version(record, 1)
        self.resubmitted(record, body=V2)
        if read:
            self.read_all(record)
        return record, v1, self.version(record, 2)

    def third_version(self, record, body=V3):
        """IERC asks again; the owner uploads ``body`` and submits v3."""
        self.asked(record, self.ierc)
        self.owner_uploads(record, body)
        with patch("apps.records.tasks.read_review_text.delay"),                 patch("apps.documents.tasks.extract_manuscript_text.delay"):
            self.submitted(record)
        self.read_all(record)
        return self.version(record, 3)

    def thread(self, record, version, quote, page=2, **extra):
        return ReviewComment.objects.create(
            record=record, author=self.ierc, body="Why?", party=Party.IERC, version=version,
            anchor_version=version, anchor_page=page, anchor_quote=quote, **extra)


class PlacesTests(ThreadPlaceTestBase):

    def test_an_unchanged_passage_moves_to_the_new_version(self):
        record, v1, v2 = self.two_versions()
        thread = self.thread(record, v1, UNTOUCHED)

        thread_places.place_threads(record)

        place = thread.places.get()
        self.assertEqual((place.version, place.outcome, place.page), (v2, ThreadPlaceOutcome.FOUND, 2))
        self.assertTrue(place.regions)
        self.assertIsNone(thread_places.outdated_since(thread))

    def test_an_edited_passage_makes_the_thread_outdated_beside_the_new_text(self):
        record, v1, v2 = self.two_versions()
        thread = self.thread(record, v1, EDITED)

        thread_places.place_threads(record)

        place = thread.places.get()
        self.assertEqual((place.outcome, place.page), (ThreadPlaceOutcome.CHANGED, 2))
        self.assertIn("two plants are feasible", place.text)
        self.assertEqual(thread_places.outdated_since(thread), 2)
        thread.refresh_from_db()
        self.assertEqual(thread.state, ThreadState.OPEN, "placing never resolves")
        # The original anchor is the thread's own, never moved.
        self.assertEqual((thread.anchor_version, thread.anchor_quote), (v1, EDITED))

    def test_nothing_is_placed_until_both_versions_are_read_and_then_once(self):
        record, v1, _ = self.two_versions(read=False)
        thread = self.thread(record, v1, UNTOUCHED)
        with patch("apps.records.tasks.read_review_text.delay"):
            thread_places.place_threads(record)
        self.assertFalse(thread.places.exists())

        self.read_all(record)
        thread_places.place_threads(record)
        thread_places.place_threads(record)
        self.assertEqual(thread.places.count(), 1)

    def test_only_open_anchored_threads_are_placed(self):
        record, v1, _ = self.two_versions()
        general = ReviewComment.objects.create(
            record=record, author=self.ierc, body="Overall fine.", party=Party.IERC, version=v1)
        resolved = self.thread(record, v1, UNTOUCHED, state=ThreadState.RESOLVED)

        thread_places.place_threads(record)

        self.assertFalse(general.places.exists())
        self.assertFalse(resolved.places.exists())

    def test_the_suggested_wording_is_looked_for_in_the_new_version(self):
        record, v1, _ = self.two_versions()
        kept = self.thread(record, v1, EDITED, suggestion="two plants are feasible")
        ignored = self.thread(record, v1, UNTOUCHED, suggestion="about 3,000 tonnes")
        plain = self.thread(record, v1, UNTOUCHED, page=2)

        thread_places.place_threads(record)

        self.assertEqual(kept.places.get().suggestion_page, 2)
        self.assertIsNone(ignored.places.get().suggestion_page)
        self.assertIsNone(plain.places.get().suggestion_page)


class FollowingTests(ThreadPlaceTestBase):
    """Decided 2026-11-09: an Outdated thread follows its newest passage and
    stays Outdated until it is resolved."""

    def test_an_outdated_thread_follows_its_new_passage_and_stays_outdated(self):
        record, v1, v2 = self.two_versions()
        thread = self.thread(record, v1, EDITED)
        thread_places.place_threads(record)
        v3 = self.third_version(record)

        thread_places.place_threads(record)

        place = thread.places.get(version=v3)
        self.assertEqual((place.outcome, place.page), (ThreadPlaceOutcome.FOUND, 2))
        self.assertIn("two plants are feasible", place.text)
        self.assertEqual(thread_places.outdated_since(thread), 2)

    def test_a_deleted_passage_reads_removed_and_is_followed_no_further(self):
        record, v1, _ = self.two_versions()
        thread = self.thread(record, v1, "small-scale digesters in Davao", page=3)
        thread_places.place_threads(record)
        v3 = self.third_version(record)
        thread_places.place_threads(record)

        place = thread.places.get(version=v3)
        self.assertEqual((place.outcome, place.page, place.text), (ThreadPlaceOutcome.REMOVED, None, ""))
        self.assertEqual(thread_places.outdated_since(thread), 3)


class WhenTests(ThreadPlaceTestBase):
    """Placing is queued when a reading finishes and when a Version is submitted."""

    PLACE = "apps.reviews.tasks.place_review_threads.delay"

    def test_finishing_a_reading_queues_placing_for_its_record(self):
        from apps.records.models import ReviewText
        from apps.records.review_text.testing import in_process_sandbox
        from apps.records.tasks import read_review_text
        from apps.records.test_review_text import SANDBOX

        record, _, _ = self.two_versions(read=False)
        text = ReviewText.objects.filter(record=record).first()
        with patch(SANDBOX, side_effect=in_process_sandbox), patch(self.PLACE) as queued:
            read_review_text(text.pk)
        queued.assert_called_once_with(record.pk)

    def test_submitting_a_version_queues_placing_after_commit(self):
        record = self.thesis(Party.IERC)
        with patch(self.PLACE) as queued, self.captureOnCommitCallbacks(execute=True):
            self.resubmitted(record, body=V2)
        queued.assert_called_once_with(record.pk)
