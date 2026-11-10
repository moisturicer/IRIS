"""
@mentions in the review discussion (ADR-032 §7 Conveniences and its IR-877
build notes 3 and 4).

A comment names the people it mentions in a list beside its body. Only people
`may_read_review` admits for the record may be named; anyone else refuses the
whole comment, so a mention never grants access and nobody is told. Each
person is notified once per comment, a draft's mentions only when *Finish
review* sends it, and a finished review sends one notice per person counting
their comments. Pinned at the REST seam.
"""

from django.urls import reverse
from rest_framework import status

from apps.notifications.models import Notification

from .test_review_comments import comment_url
from .test_review_threads import ThreadTestBase

MENTION = "Review Mention"


def mentionable_url(record):
    return reverse("record-review-mentionable", args=[record.pk])


class MentionTestBase(ThreadTestBase):
    """Every request runs its on-commit work, as a committed request would."""

    def post(self, url, as_user, body):
        with self.captureOnCommitCallbacks(execute=True):
            return super().post(url, as_user, body)

    def told(self, user, record=None):
        rows = Notification.objects.filter(recipient=user, notif_type__name=MENTION)
        if record is not None:
            rows = rows.filter(record=record)
        return list(rows.order_by("pk").values_list("message", flat=True))

    def patch(self, record, as_user, comment_id, data):
        self.client.force_authenticate(as_user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.patch(comment_url(record, comment_id), data, format="json")

    def itso_with_pool(self):
        """ITSO holds the record: `itso` opened its seat, `itso2` is in its pool."""
        return self.itso_open()


class WhoMayBeMentionedTests(MentionTestBase):

    def test_an_owner_mentions_the_adviser_who_is_told_once(self):
        record = self.at_adviser_open()

        made = self.commented(record, self.owner, "Is the consent form right?",
                              mentions=[self.adviser.pk])

        self.assertEqual(made["mentions"], [{"id": self.adviser.pk, "name": self.adviser.get_full_name()}])
        self.assertEqual(len(self.told(self.adviser, record)), 1)
        self.assertIn(record.title, self.told(self.adviser, record)[0])

    def test_a_pool_member_of_the_office_holding_the_record_may_be_mentioned(self):
        record = self.itso_with_pool()

        self.commented(record, self.owner, "Who handles the patent search?", mentions=[self.itso2.pk])

        self.assertEqual(len(self.told(self.itso2, record)), 1)

    def test_someone_who_may_not_read_the_review_is_refused_and_nobody_is_told(self):
        record = self.at_adviser_open()
        # ITSO reads every record but holds no part in this one.
        for outsider in (self.stranger, self.itso):
            with self.subTest(outsider=outsider.email):
                before = record.review_comments.count()

                response = self.comment(record, self.owner, "Look at this.",
                                        mentions=[self.adviser.pk, outsider.pk])

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(record.review_comments.count(), before)
                self.assertEqual(self.told(outsider), [])
                self.assertEqual(self.told(self.adviser), [])

    def test_the_refusal_does_not_say_whether_the_person_exists(self):
        record = self.at_adviser_open()

        stranger = self.comment(record, self.owner, "Hi.", mentions=[self.stranger.pk])
        nobody = self.comment(record, self.owner, "Hi.", mentions=[10_000_000])

        self.assertEqual(stranger.data, nobody.data)

    def test_mentions_must_be_a_list_of_people(self):
        record = self.at_adviser_open()
        for bad in ("everyone", {"id": self.adviser.pk}, [str(self.adviser.pk)], [True], [None]):
            with self.subTest(bad=bad):
                self.assertEqual(
                    self.comment(record, self.owner, "Hi.", mentions=bad).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_too_many_names_says_how_many_a_comment_may_mention(self):
        record = self.at_adviser_open()

        response = self.comment(record, self.owner, "Hi.", mentions=list(range(1, 300)))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("at most 20", response.data["detail"])

    def test_mentioning_yourself_tells_nobody(self):
        record = self.at_adviser_open()

        self.commented(record, self.owner, "Note to self.", mentions=[self.owner.pk])

        self.assertEqual(self.told(self.owner), [])

    def test_naming_someone_twice_is_one_mention(self):
        record = self.at_adviser_open()

        made = self.commented(record, self.owner, "Hi.", mentions=[self.adviser.pk, self.adviser.pk])

        self.assertEqual([m["id"] for m in made["mentions"]], [self.adviser.pk])
        self.assertEqual(len(self.told(self.adviser)), 1)

    def test_a_reply_mention_is_told_at_once(self):
        record = self.at_adviser_open()
        thread = self.commented(record, self.owner, "Is the consent form attached?")

        self.commented(record, self.adviser, "Yes, page 4.", reply_to=thread["id"],
                       mentions=[self.owner.pk])

        self.assertEqual(len(self.told(self.owner, record)), 1)


class DraftMentionTests(MentionTestBase):

    def test_a_draft_mention_is_told_only_when_the_review_is_finished(self):
        record = self.at_adviser_open()

        made = self.thread(record, self.adviser, "Clarify §3.", mentions=[self.owner.pk])
        self.assertTrue(made["is_draft"])
        self.assertEqual(self.told(self.owner), [])

        self.sent(record, self.adviser)

        self.assertEqual(len(self.told(self.owner, record)), 1)

    def test_a_finished_review_sends_one_notice_per_person_counting_their_comments(self):
        record = self.at_adviser_open()
        self.thread(record, self.adviser, "Clarify §3.", mentions=[self.owner.pk])
        self.thread(record, self.adviser, "And §4.", mentions=[self.owner.pk])
        self.thread(record, self.adviser, "A figure would help.")

        self.sent(record, self.adviser)

        told = self.told(self.owner, record)
        self.assertEqual(len(told), 1)
        self.assertIn("2 comments", told[0])

    def test_editing_a_draft_s_mentions_tells_nobody_until_it_is_sent(self):
        record = self.at_adviser_open()
        made = self.thread(record, self.adviser, "Clarify §3.")

        response = self.patch(record, self.adviser, made["id"],
                              {"body": "Clarify §3.", "mentions": [self.owner.pk]})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.told(self.owner), [])
        self.sent(record, self.adviser)
        self.assertEqual(len(self.told(self.owner, record)), 1)

    def test_a_name_removed_from_a_draft_before_it_is_sent_is_never_told(self):
        record = self.at_adviser_open()
        made = self.thread(record, self.adviser, "Clarify §3.", mentions=[self.owner.pk])
        self.patch(record, self.adviser, made["id"], {"body": "Clarify §3.", "mentions": []})

        self.sent(record, self.adviser)

        self.assertEqual(self.told(self.owner), [])

    def test_another_person_never_sees_a_draft_s_mentions(self):
        record = self.itso_with_pool()
        self.thread(record, self.itso, "Prior art?", mentions=[self.owner.pk])

        listed = self.listed(record, self.owner).data

        self.assertEqual(listed, [])


class EditedMentionTests(MentionTestBase):

    def test_someone_added_in_an_edit_is_told_once(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Is the consent form right?")

        edited = self.patch(record, self.owner, made["id"],
                            {"body": "Is the consent form right?", "mentions": [self.adviser.pk]})
        self.patch(record, self.owner, made["id"],
                   {"body": "Is the consent form right? (p. 4)", "mentions": [self.adviser.pk]})

        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        self.assertEqual([m["id"] for m in edited.data["mentions"]], [self.adviser.pk])
        self.assertEqual(len(self.told(self.adviser, record)), 1)

    def test_removing_a_name_unsends_nothing_and_adding_it_back_tells_nobody_twice(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Hi.", mentions=[self.adviser.pk])

        removed = self.patch(record, self.owner, made["id"], {"body": "Hi.", "mentions": []})
        self.patch(record, self.owner, made["id"], {"body": "Hi.", "mentions": [self.adviser.pk]})

        self.assertEqual(removed.data["mentions"], [])
        self.assertEqual(len(self.told(self.adviser, record)), 1)

    def test_an_edit_that_leaves_mentions_out_keeps_them(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Hi.", mentions=[self.adviser.pk])

        edited = self.patch(record, self.owner, made["id"], {"body": "Hello."})

        self.assertEqual([m["id"] for m in edited.data["mentions"]], [self.adviser.pk])

    def test_mentions_alone_do_not_mark_the_comment_edited(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Hi.")

        edited = self.patch(record, self.owner, made["id"], {"body": "Hi.", "mentions": [self.adviser.pk]})

        self.assertIsNone(edited.data["edited_at"])

    def test_someone_who_has_since_lost_access_does_not_stop_the_author_editing(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Hi.", mentions=[self.adviser.pk])
        self.adviser.is_active = False
        self.adviser.save(update_fields=["is_active"])

        edited = self.patch(record, self.owner, made["id"], {"body": "Hello.", "mentions": [self.adviser.pk]})

        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        self.assertEqual(edited.data["body"], "Hello.")

    def test_an_edit_naming_an_outsider_is_refused_and_changes_nothing(self):
        record = self.at_adviser_open()
        made = self.commented(record, self.owner, "Hi.")

        response = self.patch(record, self.owner, made["id"],
                              {"body": "Hi.", "mentions": [self.adviser.pk, self.stranger.pk]})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.listed(record, self.owner).data[0]["mentions"], [])
        self.assertEqual(self.told(self.adviser), [])


class MentionableTests(MentionTestBase):

    def get(self, record, as_user):
        self.client.force_authenticate(as_user)
        return self.client.get(mentionable_url(record))

    def test_a_writer_is_offered_everyone_who_may_read_the_review_but_themselves(self):
        record = self.itso_with_pool()

        response = self.get(record, self.owner)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        ids = {p["id"] for p in response.data["results"]}
        self.assertTrue({self.adviser.pk, self.itso.pk, self.itso2.pk} <= ids)
        self.assertNotIn(self.owner.pk, ids)
        self.assertNotIn(self.stranger.pk, ids)
        self.assertNotIn(self.ierc.pk, ids)
        for person in response.data["results"]:
            self.assertEqual(set(person), {"id", "name"})

    def test_everyone_offered_may_be_mentioned(self):
        record = self.itso_with_pool()
        offered = [p["id"] for p in self.get(record, self.owner).data["results"]]

        self.commented(record, self.owner, "Everyone.", mentions=offered)

    def test_someone_who_may_not_read_the_review_gets_a_404(self):
        record = self.at_adviser_open()
        for outsider in (self.stranger, self.itso):
            with self.subTest(outsider=outsider.email):
                self.assertEqual(self.get(record, outsider).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_pool_member_reads_the_review_but_may_not_write_so_is_refused(self):
        record = self.itso_with_pool()

        self.assertEqual(self.get(record, self.itso2).status_code, status.HTTP_403_FORBIDDEN)


class MentionOfAnOfficeTests(MentionTestBase):

    def test_an_office_reviewer_s_draft_mention_reaches_its_pool_member_after_finishing(self):
        record = self.itso_with_pool()
        self.thread(record, self.itso, "Can you check the claims?", mentions=[self.itso2.pk])

        self.sent(record, self.itso)

        self.assertEqual(len(self.told(self.itso2, record)), 1)
