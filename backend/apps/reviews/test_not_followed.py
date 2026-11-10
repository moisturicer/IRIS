"""A thread says why it isn't followed into a later Version (IR-1009, after
IR-876), at the REST seam. Following a passage needs both Versions' review
text; without it the card used to show nothing, which read as a bug."""
from django.utils import timezone

from apps.records.models import ReviewText
from core.enums import ReviewTextState, ThreadPlaceOutcome, ThreadState, VersionCause

from .models import ReviewComment, ThreadPlace
from .test_suggested_wording import ANCHOR, WordingTestBase


class NotFollowedTests(WordingTestBase):

    def setUp(self):
        super().setUp()
        self.record = self.at_adviser_open()
        self.made = self.thread(self.record, self.adviser, "Count again.", anchor=ANCHOR)
        self.sent(self.record, self.adviser)

    def versions(self, *states):
        """Give v1, v2, … these review-text states, creating the later Versions."""
        out = []
        for number, state in enumerate(states, start=1):
            version = (self.record.versions.get(number=1) if number == 1 else
                       self.record.versions.create(number=number, created_by=self.owner,
                                                   cause=VersionCause.REVISION))
            read = {"reader": "test-reader", "read_at": timezone.now()} if state == ReviewTextState.READ else {}
            version.review_text = ReviewText.objects.create(
                record=self.record, source_file=f"v{number}.pdf", state=state, **read)
            version.save(update_fields=["review_text"])
            out.append(version)
        return out

    def note(self):
        listed = {c["id"]: c for c in self.listed(self.record, self.owner).data}
        return listed[self.made["id"]]["not_followed"]

    def test_a_version_with_no_text_is_named(self):
        self.versions(ReviewTextState.NO_TEXT, ReviewTextState.READ)
        self.assertEqual(self.note(), {
            "version": 2, "message": "Can't follow this passage into v2: no text for v1.",
        })

    def test_a_text_not_kept_is_named(self):
        self.versions(ReviewTextState.READ, ReviewTextState.NOT_KEPT)
        self.assertEqual(self.note()["message"], "Can't follow this passage into v2: v2's text was not kept.")

    def test_while_a_text_is_being_read_or_placing_hasnt_run_it_is_looking(self):
        self.versions(ReviewTextState.READ, ReviewTextState.PENDING)
        self.assertEqual(self.note()["message"], "Looking for this passage in v2.")
        ReviewText.objects.filter(source_file="v2.pdf").update(
            state=ReviewTextState.READ, reader="test-reader", read_at=timezone.now())
        self.assertEqual(self.note()["message"], "Looking for this passage in v2.")

    def test_it_follows_from_the_newest_version_the_passage_was_found_in(self):
        _, v2, _ = self.versions(ReviewTextState.READ, ReviewTextState.READ, ReviewTextState.NO_TEXT)
        ThreadPlace.objects.create(thread_id=self.made["id"], version=v2,
                                   outcome=ThreadPlaceOutcome.FOUND, page=3, text="forty respondents")
        self.assertEqual(self.note(), {
            "version": 3, "message": "Can't follow this passage into v3: no text for v3.",
        })

    def test_nothing_is_said_where_there_is_nothing_to_explain(self):
        # Only one Version: nothing later to follow it into.
        self.versions(ReviewTextState.NO_TEXT)
        self.assertIsNone(self.note())

    def test_nothing_is_said_once_placed_removed_or_resolved(self):
        _, v2 = self.versions(ReviewTextState.READ, ReviewTextState.READ)
        place = ThreadPlace.objects.create(thread_id=self.made["id"], version=v2,
                                           outcome=ThreadPlaceOutcome.FOUND, page=3)
        self.assertIsNone(self.note(), "placed in the newest Version")

        place.outcome = ThreadPlaceOutcome.REMOVED
        place.save()
        self.record.versions.create(number=3, created_by=self.owner, cause=VersionCause.REVISION)
        self.assertIsNone(self.note(), "a removed passage is followed no further")

        place.outcome = ThreadPlaceOutcome.CHANGED
        place.save()
        ReviewComment.objects.filter(pk=self.made["id"]).update(state=ThreadState.RESOLVED)
        self.assertIsNone(self.note(), "a resolved thread isn't followed")
