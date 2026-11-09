"""Suggested wording and where a thread is now (ADR-032 §7; IR-876), at the
REST seam. Decided 2026-11-09: the wording is fixed once the thread is sent,
and accepting it is the *Addressed* answer."""
from rest_framework import status

from core.enums import ThreadPlaceOutcome, VersionCause

from .models import ReviewComment, ThreadPlace
from .test_review_threads import FIX, ThreadTestBase

ANCHOR = {"version": 1, "page": 3, "quote": "forty respondents"}
WORDING = "forty-two respondents"


def comment_url(record, comment_id):
    from django.urls import reverse
    return reverse("record-review-comment", args=[record.pk, comment_id])


class WordingTestBase(ThreadTestBase):

    def patch(self, url, as_user, body):
        self.client.force_authenticate(as_user)
        return self.client.patch(url, body, format="json")


class SuggestedWordingTests(WordingTestBase):

    def test_a_reviewer_suggests_wording_on_a_passage(self):
        record = self.at_adviser_open()

        made = self.thread(record, self.adviser, "Count again.", anchor=ANCHOR, suggestion=WORDING)

        self.assertEqual(made["suggestion"], WORDING)

    def test_wording_needs_a_passage_and_a_reviewer(self):
        record = self.at_adviser_open()
        general = self.comment(record, self.adviser, "Count again.", suggestion=WORDING)
        self.assertEqual(general.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("passage", general.data["detail"])

        owner = self.comment(record, self.owner, "Note to self.", anchor=ANCHOR, suggestion=WORDING)
        self.assertEqual(owner.status_code, status.HTTP_400_BAD_REQUEST)

        self.thread(record, self.adviser, "Count again.", anchor=ANCHOR, suggestion=WORDING)
        self.sent(record, self.adviser)
        parent = ReviewComment.objects.get(record=record, reply_to__isnull=True)
        reply = self.comment(record, self.owner, "Done.", reply_to=parent.pk, suggestion=WORDING)
        self.assertEqual(reply.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wording_can_change_while_a_draft_and_not_once_sent(self):
        record = self.at_adviser_open()
        made = self.thread(record, self.adviser, "Count again.", anchor=ANCHOR, suggestion=WORDING)

        edited = self.patch(comment_url(record, made["id"]), self.adviser, {"suggestion": "forty-one"})
        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        self.assertEqual(edited.data["suggestion"], "forty-one")

        self.sent(record, self.adviser)
        refused = self.patch(comment_url(record, made["id"]), self.adviser, {"suggestion": "forty"})
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ReviewComment.objects.get(pk=made["id"]).suggestion, "forty-one")

    def test_accepting_the_wording_is_the_addressed_answer(self):
        record = self.at_adviser_open()
        made = self.thread(record, self.adviser, "Count again.", anchor=ANCHOR,
                           suggestion=WORDING, severity=FIX)
        self.sent(record, self.adviser)

        accepted = self.answer(record, made["id"], "addressed", note="")
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        self.assertEqual(accepted.data["answer"]["kind"], "addressed")
        self.assertEqual(accepted.data["answer"]["note"], "Accepted the suggested wording.")

        declined = self.answer(record, made["id"], "declined", note="")
        self.assertEqual(declined.status_code, status.HTTP_400_BAD_REQUEST, "declining needs a reason")


class WhereItIsNowTests(WordingTestBase):

    def test_a_thread_says_where_its_passage_is_now_and_since_when_it_is_outdated(self):
        record = self.at_adviser_open()
        made = self.thread(record, self.adviser, "Count again.", anchor=ANCHOR, suggestion=WORDING)
        self.sent(record, self.adviser)
        v1 = record.versions.get(number=1)
        # Stand-ins for two later Versions' places (`thread_places` writes these).
        v2 = record.versions.create(number=2, created_by=self.owner, cause=VersionCause.REVISION)
        ThreadPlace.objects.create(thread_id=made["id"], version=v1, outcome=ThreadPlaceOutcome.FOUND,
                                   page=3, text="forty respondents")
        ThreadPlace.objects.create(thread_id=made["id"], version=v2, outcome=ThreadPlaceOutcome.CHANGED,
                                   page=4, text="forty-two respondents in all", suggestion_page=4)

        listed = {c["id"]: c for c in self.listed(record, self.owner).data}[made["id"]]

        self.assertEqual(listed["outdated_since"], 2)
        self.assertEqual(listed["place"], {
            "version": 2, "outcome": "changed", "page": 4, "text": "forty-two respondents in all",
            "regions": [], "suggestion_page": 4,
        })

    def test_a_thread_never_placed_says_so(self):
        record = self.at_adviser_open()
        made = self.thread(record, self.adviser, "Count again.", anchor=ANCHOR)
        listed = {c["id"]: c for c in self.listed(record, self.adviser).data}[made["id"]]
        self.assertEqual((listed["place"], listed["outdated_since"]), (None, None))

    def test_the_wording_is_checked_in_the_first_version_after_it_was_accepted(self):
        record = self.at_adviser_open()
        made = self.thread(record, self.adviser, "Count again.", anchor=ANCHOR, suggestion=WORDING)
        self.sent(record, self.adviser)
        v2 = record.versions.create(number=2, created_by=self.owner, cause=VersionCause.REVISION)
        v3 = record.versions.create(number=3, created_by=self.owner, cause=VersionCause.REVISION)
        # v2 was placed before the owner accepted: it can't say whether they used the wording.
        ThreadPlace.objects.create(thread_id=made["id"], version=v2, outcome=ThreadPlaceOutcome.FOUND,
                                   page=3, text="forty respondents")
        self.assertEqual(self.answer(record, made["id"], "addressed", note="").status_code, status.HTTP_200_OK)
        check = lambda: {c["id"]: c for c in self.listed(record, self.owner).data}[made["id"]]["wording_check"]  # noqa: E731
        self.assertIsNone(check())

        ThreadPlace.objects.create(thread_id=made["id"], version=v3, outcome=ThreadPlaceOutcome.CHANGED,
                                   page=4, text="forty-two respondents in all", suggestion_page=4)
        self.assertEqual(check(), {"version": 3, "page": 4})
