"""
The review discussion: `ReviewComment` (IR-419, ADR-032 §7).

Read by `may_read_review` (ADR-032 §10, IR-479 Amendment), written by the
record's participants -- its owners and anyone who has ever held a seat on it
(§7) -- on every submitted record, and never mixed with public discussion.
One class per acceptance criterion, at the REST seam (§12).
"""

from django.urls import reverse
from rest_framework import status

from core.enums import Party

from .test_decisions import DecisionTestBase
from .test_new_version import NewVersionTestBase
from .test_office_review import tracker_url


def comments_url(record):
    return reverse("record-review-comments", args=[record.pk])


def comment_url(record, comment_id):
    return reverse("record-review-comment", args=[record.pk, comment_id])


class ReviewCommentTestBase(NewVersionTestBase, DecisionTestBase):

    def comment(self, record, as_user, body="Clarify the sampling in §3.", **extra):
        return self.post(comments_url(record), as_user, {"body": body, **extra})

    def commented(self, record, as_user, body="Clarify the sampling in §3.", **extra):
        response = self.comment(record, as_user, body, **extra)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def listed(self, record, as_user):
        self.client.force_authenticate(as_user)
        return self.client.get(comments_url(record))

    def edit(self, record, as_user, comment_id, body):
        self.client.force_authenticate(as_user)
        return self.client.patch(comment_url(record, comment_id), {"body": body}, format="json")

    def at_adviser_open(self):
        record = self.new_model()
        self.adviser_seat(record)
        return record

    def ierc_asked_and_answered(self):
        """IERC asked for changes and the owner answered with v2."""
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        self.edit_title(record)
        self.submitted(record)
        return record


# --- AC: who reads the review discussion --------------------------------------------

class WhoReadsTests(ReviewCommentTestBase):

    def test_a_non_participant_gets_a_404(self):
        record = self.at_adviser_open()
        self.commented(record, self.owner)

        # ITSO reads every record, but holds no part in this one.
        for viewer in (self.itso, self.stranger):
            with self.subTest(viewer=viewer.email):
                self.assertEqual(self.listed(record, viewer).status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(
                    self.comment(record, viewer).status_code, status.HTTP_404_NOT_FOUND,
                )

    def test_the_refusal_reads_exactly_like_a_missing_record(self):
        # IR-153: ITSO sees the record, so a different 404 body would tell it
        # there is a review discussion it may not read.
        record = self.at_adviser_open()
        self.client.force_authenticate(self.itso)
        missing = self.client.get(reverse("record-review-comments", args=[record.pk + 10_000]))

        refused = self.listed(record, self.itso)

        self.assertEqual(refused.status_code, missing.status_code)
        self.assertEqual(refused.data, missing.data)
        self.assertEqual(self.comment(record, self.itso).data, missing.data)

    def test_a_participant_who_is_not_an_owner_reads_it(self):
        record = self.at_adviser_open()
        self.commented(record, self.owner, "Is the consent form attached?")

        response = self.listed(record, self.adviser)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([c["body"] for c in response.data], ["Is the consent form attached?"])

    def test_a_reviewer_whose_part_is_done_still_takes_part(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.cleared(record, self.itso)

        self.commented(record, self.itso, "Cleared; see my note on §4.")

        self.assertEqual(self.listed(record, self.itso).status_code, status.HTTP_200_OK)

    def test_a_pool_member_reads_it_but_may_not_write_in_it(self):
        # ADR-032 §10 (IR-479): an office holding the record now reads its
        # review before claiming; §7: only participants write.
        record = self.routed(Party.ITSO)
        self.commented(record, self.owner)

        self.assertEqual(self.listed(record, self.itso2).status_code, status.HTTP_200_OK)
        self.assertEqual(self.comment(record, self.itso2).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_draft_is_not_under_review(self):
        record = self.make_record()

        response = self.comment(record, self.owner)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.listed(record, self.owner).data, [])


# --- AC: a comment records its version, and reads back in order ----------------------

class CommentRecordsItsVersionTests(ReviewCommentTestBase):

    def test_an_owner_comments_and_it_is_made_against_the_latest_version(self):
        record = self.at_adviser_open()

        made = self.commented(record, self.owner, "Is the consent form attached?")

        response = self.listed(record, self.owner)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        [comment] = response.data
        self.assertEqual(comment["id"], made["id"])
        self.assertEqual(comment["body"], "Is the consent form attached?")
        self.assertEqual(comment["author_name"], self.owner.get_full_name())
        self.assertEqual(comment["version"], 1)
        self.assertIsNone(comment["reply_to"])
        self.assertIsNone(comment["edited_at"])

    def test_a_comment_after_a_new_version_is_made_against_it(self):
        record = self.routed(Party.ITSO, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.commented(record, self.ierc, "Before the revision.")
        self.asked(record, self.ierc)
        self.edit_title(record)
        self.submitted(record)

        self.commented(record, self.ierc, "After the revision.")

        response = self.listed(record, self.owner)
        self.assertEqual(
            [(c["body"], c["version"]) for c in response.data],
            [("Before the revision.", 1), ("After the revision.", 2)],
        )

    def test_a_record_with_no_version_gets_no_tag(self):
        # A record submitted before IR-416 has no versions; none is invented.
        record = self.at_adviser_open()
        record.versions.all().delete()

        made = self.commented(record, self.owner)

        self.assertIsNone(made["version"])

    def test_comments_read_back_oldest_first(self):
        record = self.at_adviser_open()
        for body in ("First.", "Second.", "Third."):
            self.commented(record, self.owner if body != "Second." else self.adviser, body)

        response = self.listed(record, self.adviser)

        self.assertEqual([c["body"] for c in response.data], ["First.", "Second.", "Third."])

    def test_an_empty_comment_is_refused(self):
        record = self.at_adviser_open()

        for body in ("", "   \n "):
            with self.subTest(body=body):
                self.assertEqual(
                    self.comment(record, self.owner, body).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )


# --- AC: replies thread, edits stamp edited_at --------------------------------------

class RepliesAndEditsTests(ReviewCommentTestBase):

    def test_a_reply_threads_under_the_comment_it_answers(self):
        record = self.at_adviser_open()
        question = self.commented(record, self.adviser, "Which sample size?")

        answer = self.commented(record, self.owner, "Forty respondents.", reply_to=question["id"])

        self.assertEqual(answer["reply_to"], question["id"])

    def test_a_reply_to_a_reply_joins_its_thread(self):
        record = self.at_adviser_open()
        question = self.commented(record, self.adviser, "Which sample size?")
        answer = self.commented(record, self.owner, "Forty.", reply_to=question["id"])

        follow_up = self.commented(record, self.adviser, "Why forty?", reply_to=answer["id"])

        self.assertEqual(follow_up["reply_to"], question["id"])

    def test_a_reply_to_another_record_s_comment_is_refused(self):
        record = self.at_adviser_open()
        elsewhere = self.at_adviser_open()
        foreign = self.commented(elsewhere, self.owner)

        response = self.comment(record, self.owner, "Hm.", reply_to=foreign["id"])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_author_edits_and_the_edit_is_stamped(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Is the consnet form attached?")

        response = self.edit(record, self.owner, made["id"], "Is the consent form attached?")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        [comment] = self.listed(record, self.owner).data
        self.assertEqual(comment["body"], "Is the consent form attached?")
        self.assertIsNotNone(comment["edited_at"])
        self.assertEqual(comment["created_at"], made["created_at"])

    def test_saving_the_same_words_is_not_an_edit(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Unchanged.")

        self.edit(record, self.owner, made["id"], "Unchanged.")

        [comment] = self.listed(record, self.owner).data
        self.assertIsNone(comment["edited_at"])

    def test_only_the_author_edits(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Mine.")

        self.assertEqual(
            self.edit(record, self.adviser, made["id"], "Not yours.").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.edit(record, self.stranger, made["id"], "Not yours.").status_code,
            status.HTTP_404_NOT_FOUND,
        )
        [comment] = self.listed(record, self.owner).data
        self.assertEqual(comment["body"], "Mine.")

    def test_a_comment_is_edited_only_through_its_own_record(self):
        record = self.at_adviser_open()
        elsewhere = self.at_adviser_open()
        made = self.commented(elsewhere, self.owner, "On the other record.")

        response = self.edit(record, self.owner, made["id"], "Moved?")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# --- AC: review comments never reach the public -------------------------------------

class NeverPublicTests(ReviewCommentTestBase):

    def test_a_published_record_s_reader_gets_none_of_the_review_discussion(self):
        record = self.at_adviser_open()
        self.commented(record, self.owner, "Internal: the consent form is late.")
        self.decided(record, self.adviser, "publish")

        # Every signed-in user reads a published record, and none of this.
        self.client.force_authenticate(self.reader)
        detail = self.client.get(reverse("record-detail", args=[record.pk]))
        tracker = self.client.get(tracker_url(record))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(tracker.status_code, status.HTTP_200_OK)
        self.assertIsNone(tracker.data["review_comments"])
        self.assertNotIn("consent form is late", str(detail.data) + str(tracker.data))
        self.assertEqual(self.listed(record, self.reader).status_code, status.HTTP_404_NOT_FOUND)


# --- The timeline reads them from the tracker ---------------------------------------

class TrackerCarriesCommentsTests(ReviewCommentTestBase):

    def test_a_participant_s_tracker_carries_the_discussion(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Is the consent form attached?")

        self.client.force_authenticate(self.adviser)
        tracker = self.client.get(tracker_url(record))

        self.assertEqual(tracker.data["review_comments"], [{**made, "can_edit": False}])

    def test_each_comment_says_whether_this_viewer_may_edit_it(self):
        # The screen follows the server: Edit is offered only where true.
        record = self.at_adviser_open()
        mine = self.commented(record, self.owner, "Mine.")
        theirs = self.commented(record, self.adviser, "Theirs.")

        # Each author is told, as they post it, that the comment is theirs.
        self.assertTrue(mine["can_edit"])
        self.assertTrue(theirs["can_edit"])
        # Read back by the owner, only the owner's own is editable.
        self.assertEqual(
            {c["body"]: c["can_edit"] for c in self.listed(record, self.owner).data},
            {"Mine.": True, "Theirs.": False},
        )
