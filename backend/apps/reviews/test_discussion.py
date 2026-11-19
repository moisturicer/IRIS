"""
Conversation comments are discussion, and a reviewer posts a thread now or
saves it as a draft (ADR-032 §7 as amended 2026-11-16; IR-1194).

At the REST seam (§12): a discussion posts at once for anyone who writes,
carries no thread field, takes no thread act, and nothing in the review counts
or closes it; a reply takes its parent's kind; an owner's thread is on a
passage; *Post* sends a reviewer's thread outside any review round and tells
the authors, and so does posting one draft on its own. The backfill is
`test_review_threads_migration.py`.
"""

from rest_framework import status

from apps.notifications.models import Notification
from core.enums import Party, ThreadState

from .models import ReviewComment, ReviewRound
from .test_review_threads import ANCHOR, FIX, ThreadTestBase

DISCUSSION, THREAD = "discussion", "thread"


class DiscussionTestBase(ThreadTestBase):

    def posted(self, record, as_user, thread_id):
        return self.act(record, as_user, thread_id, "post")

    def posted_notices(self, record):
        return list(Notification.objects.filter(record=record, notif_type__name="Review Thread Posted"))


class ADiscussionPostsAtOnceTests(DiscussionTestBase):

    def test_a_seated_reviewer_s_conversation_comment_is_seen_at_once(self):
        record = self.itso_open()

        made = self.discussed(record, self.itso, "Thanks, reading it this week.")

        self.assertEqual(made["kind"], DISCUSSION)
        self.assertFalse(made["is_draft"])
        self.assertEqual(made["party_label"], "ITSO")
        for field in ("severity", "anchor", "state", "party", "round"):
            self.assertIsNone(made[field], field)
        self.assertFalse(made["can_post"])
        for viewer in (self.owner, self.adviser, self.rdco):
            with self.subTest(viewer=viewer.email):
                self.assertIn(made["id"], self.ids(record, viewer))

    def test_a_discussion_carries_no_severity_passage_or_wording(self):
        record = self.itso_open()
        for extra in ({"severity": FIX}, {"anchor": ANCHOR},
                      {"anchor": ANCHOR, "suggestion": "sixty respondents"}):
            with self.subTest(extra=extra):
                self.assertEqual(
                    self.discuss(record, self.itso, "Hm.", **extra).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_an_unknown_kind_is_refused(self):
        record = self.itso_open()

        self.assertEqual(self.comment(record, self.itso, "Hm.", kind="memo").status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_an_owner_s_remark_on_the_whole_paper_is_discussion_not_a_thread(self):
        record = self.at_adviser_open()

        refused = self.comment(record, self.owner, "Is the consent form attached?")
        made = self.discussed(record, self.owner, "Is the consent form attached?")

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Conversation", refused.data["detail"])
        self.assertEqual((made["kind"], made["party_label"]), (DISCUSSION, "Author"))

    def test_a_reply_takes_its_parent_s_kind_wherever_it_was_typed(self):
        record = self.at_adviser_open()
        remark = self.discussed(record, self.owner, "Is the consent form attached?")
        thread = self.owner_thread(record, "Why forty?")

        to_remark = self.commented(record, self.adviser, "Yes.", reply_to=remark["id"], kind=THREAD)
        to_thread = self.commented(record, self.adviser, "Power.", reply_to=thread["id"],
                                   kind=DISCUSSION)

        self.assertEqual((to_remark["kind"], to_thread["kind"]), (DISCUSSION, THREAD))

    def test_no_thread_act_reaches_a_discussion(self):
        record = self.itso_open()
        remark = self.discussed(record, self.itso, "Reading it.")

        for act, user, body in (
            ("resolve", self.itso, None), ("severity", self.itso, {"severity": FIX}),
            ("answer", self.owner, {"answer": "addressed", "note": "Done."}),
            ("post", self.itso, None),
        ):
            with self.subTest(act=act):
                response = self.act(record, user, remark["id"], act, body)
                self.assertIn(response.status_code,
                              (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND), response.data)
        self.assertEqual(ReviewComment.objects.get(pk=remark["id"]).severity, None)


class NothingCountsADiscussionTests(DiscussionTestBase):

    def test_a_decision_closes_threads_but_not_discussion(self):
        record = self.at_adviser_open()
        remark = self.discussed(record, self.adviser, "Thanks for the revisions.")
        mine = self.owner_thread(record, "Did I attach the form?")

        self.decided(record, self.adviser, "reject", "Out of scope for this programme.")

        self.assertEqual(ReviewComment.objects.get(pk=mine["id"]).state, ThreadState.CLOSED)
        kept = ReviewComment.objects.get(pk=remark["id"])
        self.assertIsNone(kept.closed_by_decision_id)
        self.assertNotEqual(kept.state, ThreadState.CLOSED)

    def test_readiness_never_counts_a_discussion(self):
        record = self.at_rdco()
        # Not something the API writes: a discussion row that also says Must fix
        # is still nobody's review item.
        ReviewComment.objects.create(record=record, author=self.itso, body="Prior art?",
                                     party=Party.ITSO, severity=FIX, kind=DISCUSSION)

        self.assertEqual(self.thread_items(record, self.rdco), [])
        self.assertEqual(self.thread_items(record, self.owner), [])

    def test_finish_review_never_sends_a_discussion(self):
        record = self.itso_open()
        remark = self.discussed(record, self.itso, "Reading it.")
        draft = self.thread(record, self.itso, "Check the patent search.")

        self.sent(record, self.itso)

        round_ = ReviewRound.objects.get(record=record)
        self.assertEqual(ReviewComment.objects.get(pk=draft["id"]).round, round_)
        self.assertIsNone(ReviewComment.objects.get(pk=remark["id"]).round)


class PostNowTests(DiscussionTestBase):

    def test_post_sends_a_thread_now_outside_any_round_and_tells_the_authors(self):
        record = self.itso_open()

        with self.captureOnCommitCallbacks(execute=True):
            made = self.thread(record, self.itso, "Cite the prior patent.", severity=FIX,
                               anchor=ANCHOR, post_now=True)

        self.assertFalse(made["is_draft"])
        self.assertIsNone(made["round"])
        self.assertIn(made["id"], self.ids(record, self.owner))
        [notice] = self.posted_notices(record)
        self.assertEqual(notice.recipient, self.owner)
        self.assertEqual(notice.message, f'ITSO posted a Must fix on p. 3 of "{record.title}".')

        # Finish review later sends only what is still a draft.
        self.sent(record, self.itso)
        self.assertIsNone(ReviewComment.objects.get(pk=made["id"]).round)
        self.assertEqual(ReviewRound.objects.get(record=record).threads.count(), 0)

    def test_without_post_a_seated_reviewer_still_saves_a_draft(self):
        record = self.itso_open()

        with self.captureOnCommitCallbacks(execute=True):
            made = self.thread(record, self.itso, "Check the patent search.", post_now=False)

        self.assertTrue(made["is_draft"])
        self.assertTrue(made["can_post"])
        self.assertEqual(self.posted_notices(record), [])

    def test_an_owner_s_thread_tells_nobody(self):
        record = self.at_adviser_open()

        with self.captureOnCommitCallbacks(execute=True):
            self.owner_thread(record, "Why forty?", post_now=True)

        self.assertEqual(self.posted_notices(record), [])


class PostADraftTests(DiscussionTestBase):

    def test_a_writer_posts_one_draft_on_its_own(self):
        record = self.itso_open()
        draft = self.thread(record, self.itso, "Check the patent search.")
        kept = self.thread(record, self.itso, "And the trademark.")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.posted(record, self.itso, draft["id"])

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data["is_draft"])
        self.assertFalse(response.data["can_post"])
        self.assertIsNone(response.data["round"])
        self.assertIn(draft["id"], self.ids(record, self.owner))
        self.assertNotIn(kept["id"], self.ids(record, self.owner))
        [notice] = self.posted_notices(record)
        self.assertEqual(notice.message, f'ITSO posted a Suggestion on "{record.title}".')

        # Finish review sends the other draft, and not this one again.
        self.sent(record, self.itso)
        round_ = ReviewRound.objects.get(record=record)
        self.assertEqual(list(round_.threads.values_list("pk", flat=True)), [kept["id"]])

    def test_posting_a_draft_tells_the_people_it_mentions(self):
        record = self.itso_open()
        draft = self.thread(record, self.itso, "Clarify §3.", mentions=[self.owner.pk])

        with self.captureOnCommitCallbacks(execute=True):
            self.posted(record, self.itso, draft["id"])

        self.assertTrue(Notification.objects.filter(
            record=record, recipient=self.owner, notif_type__name="Review Mention").exists())

    def test_only_its_writer_posts_a_draft_and_only_once(self):
        record = self.itso_open()
        draft = self.thread(record, self.itso, "Check the patent search.")

        for viewer in (self.owner, self.rdco, self.stranger):
            with self.subTest(viewer=viewer.email):
                self.assertEqual(self.posted(record, viewer, draft["id"]).status_code,
                                 status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.posted(record, self.itso, draft["id"]).status_code, status.HTTP_200_OK)
        self.assertEqual(self.posted(record, self.itso, draft["id"]).status_code,
                         status.HTTP_400_BAD_REQUEST)


class ARoundSaysWhatItSentTests(DiscussionTestBase):

    def test_a_round_counts_its_threads_and_must_fix(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Report the response rate.", severity=FIX)
        self.thread(record, self.itso, "Consider a figure.")

        tracker = self.sent(record, self.itso)

        [shown] = tracker["review_rounds"]
        self.assertEqual((shown["threads"], shown["must_fix"]), (2, 1))
