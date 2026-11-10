"""
Comments on published papers (ADR-032 §7, amendment 2026-10-31; IR-690).

Readers discuss a published paper in a flat thread: any signed-in account
writes and replies, only the writer edits or deletes, and a deleted comment
that is part of a conversation leaves a marker with no name and no text.
Pinned at the REST seam, one class per acceptance criterion.
"""

from unittest import mock

from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.notifications.models import Notification
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RoleName

PUBLISHED = PipelineStatus.PUBLISHED


def make_user(email, role=RoleName.STUDENT, first="Test", last="User"):
    return User.objects.create_user(
        email=email, password="pw12345!", first_name=first, last_name=last,
        role=Role.objects.get_or_create(name=role)[0], is_verified=True,
    )


def make_paper(owner, status=PUBLISHED, title="Solar dryers for rural farms"):
    record = Record.objects.create(
        title=title, abstract="About " + title,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
        added_by=owner, pipeline_status=status,
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    return record


def comments_url(record):
    return reverse("record-comments", args=[record.pk])


def comment_url(record, comment_id):
    return reverse("record-comment", args=[record.pk, comment_id])


class CommentTestBase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("pc-owner@cit.edu", first="Rhea", last="Owner")
        cls.ana = make_user("pc-ana@cit.edu", first="Ana", last="Cruz")
        cls.ben = make_user("pc-ben@cit.edu", first="Ben", last="Lim")

    def setUp(self):
        self.paper = make_paper(self.owner)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def list(self, user, record=None):
        return self.as_(user).get(comments_url(record or self.paper))

    def post(self, user, body="Did you test this in the rainy season?", record=None, **extra):
        return self.as_(user).post(comments_url(record or self.paper), {"body": body, **extra}, format="json")

    def posted(self, user, body="Did you test this in the rainy season?", **extra):
        response = self.post(user, body, **extra)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def edit(self, user, comment_id, body, record=None):
        return self.as_(user).patch(comment_url(record or self.paper, comment_id), {"body": body}, format="json")

    def delete(self, user, comment_id, record=None):
        return self.as_(user).delete(comment_url(record or self.paper, comment_id))

    def thread(self, user=None):
        response = self.list(user or self.ben)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def told(self, user):
        return list(Notification.objects.filter(recipient=user).values_list("notif_type__name", "message"))


class OnlyPublishedPapersTests(CommentTestBase):

    def test_a_published_paper_lists_and_takes_comments(self):
        self.posted(self.ana)

        self.assertEqual(len(self.thread()["comments"]), 1)

    def test_a_paper_that_is_not_published_answers_like_a_hidden_record(self):
        missing = self.as_(self.ana).get(reverse("record-comments", args=[10_000_000]))
        for state in (PipelineStatus.DRAFT, PipelineStatus.IN_REVIEW, PipelineStatus.COMPLETED):
            with self.subTest(state=state):
                paper = make_paper(self.owner, status=state, title=f"Paper {state}")
                # Even its owner, who may read the record, gets no comments on it.
                for user in (self.ana, self.owner):
                    listed = self.list(user, paper)
                    self.assertEqual(listed.status_code, status.HTTP_404_NOT_FOUND)
                    self.assertEqual(listed.data, missing.data)
                    self.assertEqual(self.post(user, record=paper).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_paper_that_stops_being_public_takes_its_comments_with_it_and_deletes_nothing(self):
        made = self.posted(self.ana)
        Record.objects.filter(pk=self.paper.pk).update(pipeline_status=PipelineStatus.IN_REVIEW)

        self.assertEqual(self.list(self.ana).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.edit(self.ana, made["id"], "Changed").status_code, status.HTTP_404_NOT_FOUND)

        Record.objects.filter(pk=self.paper.pk).update(pipeline_status=PUBLISHED)
        self.assertEqual([c["id"] for c in self.thread()["comments"]], [made["id"]])

    def test_signing_in_is_required(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(comments_url(self.paper)).status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class WritingAndReplyingTests(CommentTestBase):

    def test_any_signed_in_account_comments_and_its_owner_too(self):
        self.posted(self.ana, "Ana's question.")
        self.posted(self.owner, "The owner's note.")

        listed = self.thread()["comments"]

        self.assertEqual([c["body"] for c in listed], ["Ana's question.", "The owner's note."])

    def test_each_comment_carries_who_when_and_whether_edited(self):
        made = self.posted(self.ana, "Hello.")

        self.assertEqual(set(made), {"id", "author_name", "body", "created_at", "edited_at", "is_author",
                                     "can_edit", "can_report", "reply_to", "deletion_kind"})
        self.assertEqual(made["author_name"], "Ana Cruz")
        self.assertIsNone(made["edited_at"])
        self.assertIsNone(made["reply_to"])
        self.assertIsNone(made["deletion_kind"])

    def test_an_account_with_no_name_never_shows_its_email(self):
        nameless = make_user("pc-nameless@cit.edu", first="", last="")

        made = self.posted(nameless, "Hello.")

        self.assertEqual(made["author_name"], "IRIS user")

    def test_the_author_badge_marks_a_writer_who_owns_the_paper(self):
        self.posted(self.owner, "Thanks for reading.")
        self.posted(self.ana, "Great work.")

        badges = [c["is_author"] for c in self.thread()["comments"]]

        self.assertEqual(badges, [True, False])

    def test_the_thread_is_flat_and_oldest_first_and_a_reply_names_its_comment(self):
        first = self.posted(self.ana, "First.")
        second = self.posted(self.ben, "Second.")
        reply = self.posted(self.owner, "Answering Ana.", reply_to=first["id"])
        # A reply to a reply is still a comment in the same flat thread.
        again = self.posted(self.ana, "Answering the owner.", reply_to=reply["id"])

        listed = self.thread()["comments"]

        self.assertEqual([c["id"] for c in listed], [first["id"], second["id"], reply["id"], again["id"]])
        self.assertEqual(listed[2]["reply_to"], first["id"])

    def test_a_reply_must_answer_a_comment_on_the_same_paper_that_is_not_deleted(self):
        other_paper = make_paper(self.owner, title="Another paper")
        response = self.post(self.ana, "On the other paper.", record=other_paper)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        gone = self.posted(self.ana, "Will be deleted.")
        self.delete(self.ana, gone["id"])

        for reply_to in (response.data["id"], gone["id"], 10_000_000, "x"):
            with self.subTest(reply_to=reply_to):
                self.assertEqual(self.post(self.ben, "Reply.", reply_to=reply_to).status_code,
                                 status.HTTP_400_BAD_REQUEST)

    def test_a_comment_is_plain_text_up_to_2000_characters_with_its_line_breaks(self):
        made = self.posted(self.ana, "  <b>Line one</b>\nLine two  ")

        self.assertEqual(made["body"], "<b>Line one</b>\nLine two")
        self.assertEqual(self.post(self.ana, "x" * 2000).status_code, status.HTTP_201_CREATED)
        for bad in ("x" * 2001, "   ", None, 5):
            with self.subTest(bad=str(bad)[:10]):
                self.assertEqual(self.post(self.ana, bad).status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_response_counts_the_comments_that_are_not_deleted(self):
        keep = self.posted(self.ana, "Stays.")
        gone = self.posted(self.ben, "Goes.")
        self.posted(self.owner, "Reply to Ben.", reply_to=gone["id"])
        self.delete(self.ben, gone["id"])

        listed = self.thread()

        self.assertEqual(listed["count"], 2)
        self.assertIn(keep["id"], [c["id"] for c in listed["comments"]])

    def test_report_is_not_offered_until_reports_exist(self):
        # IR-691 adds reporting; until then the server offers nothing it can't do.
        self.posted(self.ana)

        self.assertFalse(self.thread(self.ben)["comments"][0]["can_report"])


class PostingIsRateLimitedTests(CommentTestBase):

    def test_posting_past_the_budget_is_refused_but_reading_is_not(self):
        from apps.records.public_comments import CommentPostBurstThrottle

        rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "public_comment_burst": "2/minute"}
        with mock.patch.object(CommentPostBurstThrottle, "THROTTLE_RATES", rates):
            self.posted(self.ana, "One.")
            self.posted(self.ana, "Two.")
            self.assertEqual(self.post(self.ana, "Three.").status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertEqual(self.list(self.ana).status_code, status.HTTP_200_OK)
            # Another person has their own budget.
            self.posted(self.ben, "Ben's first.")


class EditingTests(CommentTestBase):

    def test_the_writer_edits_and_it_reads_edited_without_its_earlier_wording(self):
        made = self.posted(self.ana, "Frist draft.")

        edited = self.edit(self.ana, made["id"], "First draft.")

        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        self.assertEqual(edited.data["body"], "First draft.")
        self.assertIsNotNone(edited.data["edited_at"])
        self.assertNotIn("Frist", str(self.thread()))

    def test_only_the_writer_edits_or_deletes_not_even_the_paper_s_owner(self):
        made = self.posted(self.ana, "Mine.")

        for other in (self.ben, self.owner):
            with self.subTest(other=other.email):
                self.assertEqual(self.edit(other, made["id"], "Not yours.").status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self.delete(other, made["id"]).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.thread()["comments"][0]["body"], "Mine.")

    def test_only_the_writer_is_offered_edit(self):
        self.posted(self.ana, "Mine.")

        self.assertTrue(self.thread(self.ana)["comments"][0]["can_edit"])
        self.assertFalse(self.thread(self.ben)["comments"][0]["can_edit"])

    def test_a_deleted_comment_cannot_be_edited_or_deleted_again(self):
        made = self.posted(self.ana, "Gone soon.")
        self.posted(self.ben, "Reply.", reply_to=made["id"])
        self.delete(self.ana, made["id"])

        self.assertEqual(self.edit(self.ana, made["id"], "Back?").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.delete(self.ana, made["id"]).status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_comment_on_another_paper_is_not_found_here(self):
        other_paper = make_paper(self.owner, title="Another paper")
        response = self.post(self.ana, "Elsewhere.", record=other_paper)

        self.assertEqual(self.edit(self.ana, response.data["id"], "Here?").status_code, status.HTTP_404_NOT_FOUND)


class DeletingTests(CommentTestBase):

    def test_a_standalone_comment_deleted_by_its_writer_disappears(self):
        made = self.posted(self.ana, "Never mind.")

        response = self.delete(self.ana, made["id"])

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.thread()["comments"], [])

    def test_a_deleted_comment_with_a_reply_leaves_a_marker_with_no_name_and_no_text(self):
        made = self.posted(self.ana, "Secret wording.")
        reply = self.posted(self.ben, "Good point.", reply_to=made["id"])

        self.delete(self.ana, made["id"])
        listed = self.thread()["comments"]

        marker = listed[0]
        self.assertEqual(marker["id"], made["id"])
        self.assertEqual(marker["deletion_kind"], "writer")
        self.assertIsNone(marker["author_name"])
        self.assertIsNone(marker["body"])
        self.assertFalse(marker["is_author"])
        self.assertFalse(marker["can_edit"])
        self.assertNotIn("Secret wording", str(listed))
        self.assertEqual(listed[1]["id"], reply["id"])

    def test_a_deleted_reply_leaves_a_marker_too_so_the_conversation_keeps_its_shape(self):
        made = self.posted(self.ana, "Question.")
        reply = self.posted(self.ben, "Answer.", reply_to=made["id"])

        self.delete(self.ben, reply["id"])
        self.delete(self.ana, made["id"])
        listed = self.thread()["comments"]

        self.assertEqual([(c["id"], c["deletion_kind"]) for c in listed],
                         [(made["id"], "writer"), (reply["id"], "writer")])
        self.assertEqual(self.thread()["count"], 0)

    def test_removing_a_paper_removes_its_whole_conversation(self):
        from apps.records.models import PublicComment
        made = self.posted(self.ana, "Question.")
        self.posted(self.ben, "Answer.", reply_to=made["id"])

        self.paper.delete()

        self.assertFalse(PublicComment.objects.exists())

    def test_the_text_stays_stored_but_no_response_carries_it(self):
        from apps.records.models import PublicComment

        made = self.posted(self.ana, "Kept for reports.")
        self.posted(self.ben, "Reply.", reply_to=made["id"])
        self.delete(self.ana, made["id"])

        stored = PublicComment.objects.get(pk=made["id"])
        self.assertEqual(stored.body, "Kept for reports.")
        self.assertEqual(stored.deleted_by, self.ana)
        self.assertIsNotNone(stored.deleted_at)
        for user in (self.ana, self.ben, self.owner):
            self.assertNotIn("Kept for reports", str(self.thread(user)))


class NotificationTests(CommentTestBase):

    def post(self, *args, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return super().post(*args, **kwargs)

    def test_the_owners_hear_of_a_new_comment_by_someone_else(self):
        co_owner = make_user("pc-co@cit.edu", first="Co", last="Owner")
        RecordOwner.objects.create(record=self.paper, user=co_owner)

        self.posted(self.ana, "Nice.")
        self.posted(self.owner, "Thanks.")

        self.assertEqual(len(self.told(self.owner)), 1)
        self.assertIn(self.paper.title, self.told(self.owner)[0][1])
        # The owner's own comment told the other owner, never the owner.
        self.assertEqual(len(self.told(co_owner)), 2)

    def test_a_writer_hears_of_a_reply_and_owners_hear_only_of_top_level_comments(self):
        made = self.posted(self.ana, "Question.")

        self.posted(self.ben, "Answer.", reply_to=made["id"])

        self.assertEqual(len(self.told(self.ana)), 1)
        self.assertIn("Ben Lim", self.told(self.ana)[0][1])
        self.assertEqual(len(self.told(self.owner)), 1)  # Ana's comment, not Ben's reply

    def test_replying_to_yourself_tells_nobody_new(self):
        made = self.posted(self.ana, "Question.")

        self.posted(self.ana, "Also this.", reply_to=made["id"])

        self.assertEqual(self.told(self.ana), [])


class AskIrisNeverReadsCommentsTests(CommentTestBase):

    def test_no_ai_module_reads_the_comments_table(self):
        import pathlib

        ai = pathlib.Path(__file__).resolve().parents[1] / "ai"
        readers = [p for p in ai.rglob("*.py") if "PublicComment" in p.read_text(encoding="utf-8")]

        self.assertEqual(readers, [])
