"""
Acting on a review takes a seat; a removed Adviser stops reading it (IR-1226).

ADR-032 §10, *Amendment, 2026-11-18 (IR-1226)*, with its correction of point 2
(an Adviser seat counts only while its holder is the record's Adviser), and
ADR-022 Amendment 7. Pinned at the REST seam, one class per point.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest, UploadSlot

from core.enums import AssignmentState, Party, RoleName, SeatState

from . import seats
from .models import RecordAssignment, ReviewComment, ReviewerSeat
from .test_review_comments import comment_url
from .test_review_threads import ThreadTestBase, comments_url
from apps.accounts.tests import make_user


def replace_url(record):
    return reverse("record-replace-adviser", args=[record.pk])


class SeatTestBase(ThreadTestBase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.itso_coordinator = make_user("seats-itso-coord@cit.edu", RoleName.ITSO)
        cls.itso_coordinator.is_office_coordinator = True
        cls.itso_coordinator.save(update_fields=["is_office_coordinator"])

    def get(self, url, as_user):
        self.client.force_authenticate(as_user)
        return self.client.get(url)

    def replace_adviser(self, record, adviser=None):
        """RDCO names `adviser` (the other Adviser by default), who opens their seat."""
        adviser = adviser or self.other_adviser
        response = self.post(replace_url(record), self.rdco, {"adviser": adviser.pk, "reason": "On leave."})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        record.refresh_from_db()
        seats.open_review(ReviewerSeat.objects.get(pk=response.data["seat"]), adviser)

    def published_by(self, record, adviser):
        """`adviser` sends the paper to RDCO, which publishes it."""
        response = self.accept(record, [{"party": Party.RDCO, "nominees": [self.rdco.pk]}], as_user=adviser)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.opened_seat(record, Party.RDCO, self.rdco)
        self.decided(record, self.rdco, "publish")

    def itso_seat(self, record, reviewer=None):
        return ReviewerSeat.objects.get(
            assignment__record=record, assignment__party=Party.ITSO,
            reviewer=reviewer or self.itso, state__in=[SeatState.ASSIGNED, SeatState.IN_REVIEW],
        )

    def withdrawn_itso_reviewer(self):
        """ITSO's seat holder sent a Must fix thread, then their coordinator withdrew the seat."""
        record = self.itso_open()
        self.made = self.must_fix_sent(record, self.itso)
        seats.withdraw(self.itso_seat(record), self.itso_coordinator)
        return record

    # Document requests and office files (ADR-022 Amendment 7).

    def ask_for_documents(self, record, as_user):
        slot = UploadSlot.objects.get_or_create(
            name="Ethics Clearance", record_type=record.record_type, record=None,
        )[0]
        response = self.post(
            reverse("record-document-requests", args=[record.pk]), as_user,
            {"message": "Please send the signed forms.", "items": [{"slot": slot.pk}]},
        )
        if response.status_code == status.HTTP_201_CREATED:
            # A draft until Finish review sends it (ADR-022 Amendment 9, IR-1325).
            from apps.documents.testing import send_drafted_requests

            send_drafted_requests(self, record, as_user, response.data["party"])
        return response

    def withdraw_request(self, request_id, as_user):
        self.client.force_authenticate(as_user)
        return self.client.patch(
            reverse("document-request-detail", args=[request_id]), {"action": "withdraw"}, format="json",
        )

    def attach(self, record, as_user):
        self.client.force_authenticate(as_user)
        return self.client.post(reverse("record-file-upload"), {
            "record": record.pk,
            "file": SimpleUploadedFile("notes.png", b"\x89PNG\r\n\x1a\nOffice notes", content_type="image/png"),
        }, format="multipart")


# --- point 2: reading ----------------------------------------------------------------

class WhoReadsAfterRemovalTests(SeatTestBase):

    def test_a_replaced_adviser_reads_none_of_a_published_paper_s_review(self):
        record = self.at_adviser_open()
        self.thread(record, self.adviser, "Clarify the sampling.")
        self.replace_adviser(record)
        self.published_by(record, self.other_adviser)

        self.assertEqual(self.get(comments_url(record), self.adviser).status_code, status.HTTP_404_NOT_FOUND)
        detail = self.detail(record, self.adviser)
        self.assertFalse(detail["is_participant"])
        # The new Adviser still reads it.
        self.assertEqual(self.get(comments_url(record), self.other_adviser).status_code, status.HTTP_200_OK)

    def test_a_replaced_adviser_who_had_finished_an_earlier_adviser_seat_still_loses_it(self):
        record = self.at_adviser_open()
        # An earlier Adviser review of this record, which they finished.
        earlier = RecordAssignment.objects.create(
            record=record, party=Party.ADVISER, state=AssignmentState.COMPLETED,
        )
        ReviewerSeat.objects.create(assignment=earlier, reviewer=self.adviser, state=SeatState.DONE)
        self.replace_adviser(record)
        self.published_by(record, self.other_adviser)

        self.assertEqual(self.get(comments_url(record), self.adviser).status_code, status.HTTP_404_NOT_FOUND)

    def test_an_adviser_put_back_reads_again(self):
        record = self.at_adviser_open()
        self.replace_adviser(record)
        self.replace_adviser(record, self.adviser)
        self.published_by(record, self.adviser)

        self.assertEqual(self.get(comments_url(record), self.adviser).status_code, status.HTTP_200_OK)
        self.assertEqual(self.get(comments_url(record), self.other_adviser).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_removed_office_reviewer_still_reads_the_review(self):
        record = self.withdrawn_itso_reviewer()
        self.assertEqual(self.get(comments_url(record), self.itso).status_code, status.HTTP_200_OK)
        self.assertTrue(self.detail(record, self.itso)["is_participant"])


# --- point 1: acting takes a seat that was not withdrawn ------------------------------

class ARemovedReviewerActsOnNothingTests(SeatTestBase):

    def test_they_post_reply_and_comment_nothing(self):
        record = self.withdrawn_itso_reviewer()
        refused = status.HTTP_403_FORBIDDEN
        self.assertEqual(self.comment(record, self.itso, "One more thing.").status_code, refused)
        self.assertEqual(self.comment(record, self.itso, "Agreed.", reply_to=self.made["id"]).status_code, refused)
        self.assertEqual(self.discuss(record, self.itso, "A general remark.").status_code, refused)

    def test_they_edit_resolve_and_reopen_nothing_and_are_offered_none_of_it(self):
        record = self.withdrawn_itso_reviewer()
        thread = self.made["id"]
        self.assertEqual(self.edit(record, self.itso, thread, "Changed.").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.act(record, self.itso, thread, "resolve").status_code, status.HTTP_403_FORBIDDEN)

        [listed] = [c for c in self.listed(record, self.itso).data if c["id"] == thread]
        self.assertEqual(
            (listed["can_edit"], listed["can_resolve"], listed["can_reopen"]), (False, False, False),
        )
        self.assertNotIn("comment_review", self.detail(record, self.itso)["capabilities"])

    def test_resolved_by_someone_else_they_cannot_reopen_it(self):
        record = self.withdrawn_itso_reviewer()
        thread = self.made["id"]
        self.answer(record, thread)
        seats.claim(self.assignment(record, Party.ITSO), self.itso2)
        seats.open_review(self.itso_seat(record, self.itso2), self.itso2)
        self.assertEqual(self.act(record, self.itso2, thread, "resolve").status_code, status.HTTP_200_OK)

        self.assertEqual(self.act(record, self.itso, thread, "reopen").status_code, status.HTTP_403_FORBIDDEN)


class WhoStillActsTests(SeatTestBase):

    def test_an_owner_and_a_seated_reviewer_act(self):
        record = self.itso_open()
        self.assertEqual(self.discuss(record, self.itso).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.discuss(record, self.owner).status_code, status.HTTP_201_CREATED)
        self.assertIn("comment_review", self.detail(record, self.itso)["capabilities"])



class AFinishedReviewerOnlyDiscussesTests(SeatTestBase):
    """
    IR-1226, decided 2026-11-19: once a seat is done its holder reads, writes
    in Conversation and replies in a thread, and edits those. They start,
    edit, resolve, reopen and re-rate no thread, and act on no document.
    """

    def done_itso(self):
        record = self.itso_open()
        self.made = self.thread(record, self.itso, "Note the licence.")
        self.question = self.owner_thread(record, "Which licence?")
        self.sent(record, self.itso)
        self.cleared(record, self.itso)
        seat = ReviewerSeat.objects.get(assignment__record=record, reviewer=self.itso)
        self.assertEqual(seat.state, SeatState.DONE)
        return record

    def test_they_still_write_in_conversation_and_reply(self):
        record = self.done_itso()
        self.assertEqual(self.discuss(record, self.itso).status_code, status.HTTP_201_CREATED)
        reply = self.comment(record, self.itso, "MIT.", reply_to=self.question["id"])
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED, reply.data)
        edited = self.client.patch(
            comment_url(record, reply.data["id"]), {"body": "MIT, see p. 2."}, format="json",
        )
        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        self.assertIn("comment_review", self.detail(record, self.itso)["capabilities"])

    def test_they_start_edit_resolve_reopen_and_re_rate_no_thread(self):
        record = self.done_itso()
        new = self.comment(record, self.itso, "One more note.")
        self.assertEqual(new.status_code, status.HTTP_403_FORBIDDEN, new.data)
        self.assertIn("Your part of this review is finished", new.data["detail"])
        self.client.force_authenticate(self.itso)
        edit = self.client.patch(comment_url(record, self.made["id"]), {"body": "Changed."}, format="json")
        self.assertEqual(edit.status_code, status.HTTP_403_FORBIDDEN, edit.data)
        for act, body in (("resolve", None), ("severity", {"severity": "must_fix"})):
            with self.subTest(act):
                self.assertIn(
                    self.act(record, self.itso, self.made["id"], act, body).status_code,
                    (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN),
                )
        self.assertEqual(ReviewComment.objects.get(pk=self.made["id"]).state, "open")

        offered = set(self.detail(record, self.itso)["capabilities"])
        self.assertFalse({"start_thread", "open_general_thread"} & offered)
        [listed] = [c for c in self.listed(record, self.itso).data if c["id"] == self.made["id"]]
        self.assertEqual(
            {k: listed[k] for k in ("can_edit", "can_resolve", "can_reopen", "can_change_severity")},
            {"can_edit": False, "can_resolve": False, "can_reopen": False, "can_change_severity": False},
        )

    def test_they_act_on_no_document_request(self):
        record = self.itso_open()
        # A colleague keeps ITSO's review running, and asks for a document
        # after this reviewer has cleared: the party's request, not theirs.
        ReviewerSeat.objects.create(
            assignment=self.assignment(record, Party.ITSO), reviewer=self.itso2, state=SeatState.IN_REVIEW,
        )
        self.cleared(record, self.itso)
        asked = self.ask_for_documents(record, self.itso2)
        self.assertEqual(asked.status_code, status.HTTP_201_CREATED, asked.data)

        self.assertEqual(self.withdraw_request(asked.data["id"], self.itso).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.ask_for_documents(record, self.itso).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.attach(record, self.itso).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.withdraw_request(asked.data["id"], self.itso2).status_code, status.HTTP_200_OK)


class DocumentRequestsTakeASeatTests(SeatTestBase):
    """ADR-022 Amendment 7: creating, deciding and withdrawing take a seat on the party."""

    def test_an_unseated_member_and_a_coordinator_cannot_ask(self):
        record = self.itso_open()
        for unseated in (self.itso2, self.itso_coordinator):
            with self.subTest(unseated.email):
                self.assertEqual(self.ask_for_documents(record, unseated).status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self.detail(record, unseated)["can_request_document"], [])
        self.assertEqual(self.ask_for_documents(record, self.itso).status_code, status.HTTP_201_CREATED)

    def test_a_removed_reviewer_cannot_withdraw_their_request_and_whoever_holds_the_seat_can(self):
        record = self.itso_open()
        asked = self.ask_for_documents(record, self.itso).data
        seats.reassign(self.itso_seat(record), self.itso_coordinator, self.itso2, reason="Leave.")

        request = DocumentRequest.objects.get(record=record)
        self.assertEqual(request.state, "open", "a removal leaves the request open")
        self.assertEqual(self.withdraw_request(asked["id"], self.itso).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.withdraw_request(asked["id"], self.itso_coordinator).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.withdraw_request(asked["id"], self.itso2).status_code, status.HTTP_200_OK)


class OfficeFilesTakeASeatTests(SeatTestBase):

    def test_only_a_seat_holder_attaches_a_file(self):
        record = self.itso_open()
        for unseated in (self.itso2, self.itso_coordinator):
            with self.subTest(unseated.email):
                self.assertEqual(self.attach(record, unseated).status_code, status.HTTP_403_FORBIDDEN)
                self.assertNotIn("attach_file", self.detail(record, unseated)["capabilities"])
        self.assertEqual(self.attach(record, self.itso).status_code, status.HTTP_201_CREATED)

    def test_a_removed_reviewer_attaches_nothing(self):
        record = self.withdrawn_itso_reviewer()
        self.assertEqual(self.attach(record, self.itso).status_code, status.HTTP_403_FORBIDDEN)


# --- point 5 and 6: unsent drafts are discarded, requests and sent work stay ----------

class DraftsDiscardedAtRemovalTests(SeatTestBase):

    def itso_with_work(self):
        """ITSO's reviewer sent a Must fix, saved a draft and asked for a document."""
        record = self.itso_open()
        self.sent_thread = self.must_fix_sent(record, self.itso)
        self.draft = self.thread(record, self.itso, "Not sent yet.")
        self.assertEqual(self.ask_for_documents(record, self.itso).status_code, status.HTTP_201_CREATED)
        return record

    def assert_drafts_gone_and_work_kept(self, record):
        self.assertFalse(ReviewComment.objects.filter(pk=self.draft["id"]).exists())
        self.assertTrue(ReviewComment.objects.filter(pk=self.sent_thread["id"], is_draft=False).exists())
        self.assertEqual(DocumentRequest.objects.get(record=record).state, "open")

    def test_reassigning_discards_their_drafts_and_keeps_what_they_sent_and_asked(self):
        record = self.itso_with_work()
        seats.reassign(self.itso_seat(record), self.itso_coordinator, self.itso2, reason="Leave.")
        self.assert_drafts_gone_and_work_kept(record)

    def test_withdrawing_discards_their_drafts(self):
        record = self.itso_with_work()
        seats.withdraw(self.itso_seat(record), self.itso_coordinator)
        self.assert_drafts_gone_and_work_kept(record)

    def test_replacing_the_adviser_discards_their_drafts(self):
        record = self.at_adviser_open()
        draft = self.thread(record, self.adviser, "Not sent yet.")
        self.replace_adviser(record)
        self.assertFalse(ReviewComment.objects.filter(pk=draft["id"]).exists())

    def test_a_decision_discards_the_other_reviewers_drafts_not_the_decider_s(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        itso_draft = self.thread(record, self.itso, "Not sent yet.")
        self.opened_seat(record, Party.RDCO, self.rdco)
        rdco_draft = self.thread(record, self.rdco, "Mine, not sent.")

        self.decided(record, self.rdco, "reject", "Duplicates a thesis published in 2023.")

        self.assertFalse(ReviewComment.objects.filter(pk=itso_draft["id"]).exists())
        self.assertTrue(ReviewComment.objects.filter(pk=rdco_draft["id"]).exists())


# --- point 4: the warning's counts come from the server ---------------------------------

NOTHING_LEFT = {"drafts": 0, "open_threads": 0, "document_requests": 0, "revision_requests": 0}


class WarningCountsTests(SeatTestBase):

    def console_row(self, record, reviewer):
        self.client.force_authenticate(self.itso_coordinator)
        response = self.client.get(reverse("reviews-office"))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        [row] = [r for r in response.data["rows"] if r["record"] == record.pk and r["reviewer"] == reviewer.pk]
        return row

    def test_replace_adviser_carries_what_the_adviser_leaves(self):
        record = self.at_adviser_open()
        self.must_fix_sent(record, self.adviser)
        self.thread(record, self.adviser, "Not sent yet.")
        self.assertEqual(self.ask_for_documents(record, self.adviser).status_code, status.HTTP_201_CREATED)

        leaving = self.detail(record, self.rdco)["adviser_leaving"]
        self.assertEqual(leaving["name"], self.adviser.get_full_name())
        self.assertEqual(
            leaving["unresolved"],
            {"drafts": 1, "open_threads": 1, "document_requests": 1, "revision_requests": 0},
        )
        # Only RDCO, which is offered the act, is told.
        self.assertIsNone(self.detail(record, self.owner)["adviser_leaving"])

    def test_the_console_offers_withdraw_with_what_the_reviewer_leaves(self):
        record = self.itso_open()
        self.thread(record, self.itso, "Not sent yet.")

        row = self.console_row(record, self.itso)
        self.assertIn("withdraw", row["actions"])
        self.assertEqual(row["unresolved"], {**NOTHING_LEFT, "drafts": 1})
        self.assertFalse(row["withdraw_completes_office"])

    def test_the_console_says_when_withdrawing_finishes_the_office(self):
        record = self.itso_open()
        ReviewerSeat.objects.create(
            assignment=self.assignment(record, Party.ITSO), reviewer=self.itso2, state=SeatState.DONE,
        )
        self.assertTrue(self.console_row(record, self.itso)["withdraw_completes_office"])

    def test_the_decision_names_what_each_closing_reviewer_leaves(self):
        record = self.routed(Party.ITSO)
        self.opened_seat(record, Party.ITSO, self.itso)
        self.thread(record, self.itso, "Not sent yet.")
        self.opened_seat(record, Party.RDCO, self.rdco)

        [itso] = [a for a in self.detail(record, self.rdco)["decision"]["closes"]["assignments"]
                  if a["party"] == Party.ITSO]
        self.assertEqual(
            itso["leaving"], [{"name": self.itso.get_full_name(), "unresolved": {**NOTHING_LEFT, "drafts": 1}}],
        )
