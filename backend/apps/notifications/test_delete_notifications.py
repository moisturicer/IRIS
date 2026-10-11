"""
Who is told when an owner deletes a record (IR-517, ADR-032 §10 Amendment of
2026-10-11).

Until IR-517 none of the owner's three deletes (IR-508) told anyone, and
withdrawing a record from review left its document requests open. Settled with
the project lead:

* **withdraw_submission:** each holder of an open seat is told their review is
  closed, in-app only, plus a clause when their party's document request is
  withdrawn. Office pools are not told. Open document requests are withdrawn.
* **every act:** every *other* owner is told, in-app and by email.
* **request_deletion:** RDCO is told too, in-app and by email.
* **links:** a deleted record is a 404 for everyone, so withdrawal and delete
  notices carry no record; a delete request's notices link the record.

**Seam: the API.** Notices are read as each user through `GET /notifications/`;
outbound email is patched where it leaves the system, the one mock allowed.
"""

from unittest import mock

from django.urls import reverse
from rest_framework import status

from apps.accounts.models import User
from apps.documents.models import DocumentRequest
from apps.records.models import RecordOwner
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import DocumentRequestState, Party, RoleName

NOTIFICATIONS = "/api/v1/notifications/"
SEND_EMAIL = "apps.notifications.services.send_email_async"


class DeleteNotificationTestBase(DecisionTestBase):

    def notices(self, user, type_name):
        self.client.force_authenticate(user)
        response = self.client.get(NOTIFICATIONS, {"page_size": 100})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return [row for row in rows if row["notif_type_name"] == type_name]

    def delete_as_owner(self, record):
        """The owner's delete, with its after-commit notices run and its email captured."""
        self.client.force_authenticate(self.owner)
        with mock.patch(SEND_EMAIL) as send, self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(reverse("record-detail", args=[record.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        return [
            (tuple(call.kwargs["recipient_list"]), call.kwargs["subject"])
            for call in send.call_args_list
        ]

    def co_owned(self, record):
        RecordOwner.objects.create(record=record, user=self.reader, is_primary=False)
        return record

    def request_documents(self, record, as_user):
        response = self.post(
            reverse("record-document-requests", args=[record.pk]), as_user,
            {"message": "Please attach the consent form.", "items": [{"label": "Consent form"}]},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def published(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")
        return record


# --- withdraw_submission ----------------------------------------------------------------

class WithdrawingARecordInReviewTests(DeleteNotificationTestBase):

    def withdrawn_from_offices(self):
        """ITSO seated with an open document request; IERC only a pool; a co-owner."""
        record = self.co_owned(self.routed(Party.ITSO, Party.IERC))
        self.opened_seat(record, Party.ITSO, self.itso)
        self.request_documents(record, self.itso)
        return record, self.delete_as_owner(record)

    def test_a_seated_reviewer_is_told_their_review_and_request_are_closed(self):
        self.withdrawn_from_offices()

        [notice] = self.notices(self.itso, "Record Withdrawn")
        self.assertIn("withdrew", notice["message"])
        self.assertIn("your review is closed", notice["message"])
        self.assertIn("Your office's document request is withdrawn", notice["message"])
        self.assertIsNone(notice["record"], "a deleted record is a 404: no link")

    def test_an_office_pool_is_not_told(self):
        self.withdrawn_from_offices()

        for member in (self.ierc, self.ierc2):
            with self.subTest(member=member.email):
                self.assertEqual(self.notices(member, "Record Withdrawn"), [])

    def test_the_adviser_whose_turn_had_ended_is_not_told(self):
        self.withdrawn_from_offices()

        self.assertEqual(self.notices(self.adviser, "Record Withdrawn"), [])

    def test_the_other_owner_is_told_in_app_and_by_email_and_the_acting_owner_is_not(self):
        record, emails = self.withdrawn_from_offices()

        [notice] = self.notices(self.reader, "Record Withdrawn")
        self.assertIn("can't be restored", notice["message"])
        self.assertIsNone(notice["record"])
        self.assertEqual(self.notices(self.owner, "Record Withdrawn"), [])
        self.assertEqual([recipients for recipients, _ in emails], [(self.reader.email,)])

    def test_open_document_requests_are_withdrawn(self):
        record, _ = self.withdrawn_from_offices()

        request = DocumentRequest.objects.get(record_id=record.pk)
        self.assertEqual(request.state, DocumentRequestState.WITHDRAWN)
        self.assertIsNotNone(request.closed_at)
        self.assertIsNone(request.closed_by_decision)

    def test_the_adviser_at_entry_is_told_and_their_request_is_named_as_theirs(self):
        record = self.at_adviser()
        self.request_documents(record, self.adviser)

        self.delete_as_owner(record)

        [notice] = self.notices(self.adviser, "Record Withdrawn")
        self.assertIn("your review is closed", notice["message"])
        self.assertIn("Your document request is withdrawn", notice["message"])


# --- delete_record ----------------------------------------------------------------------

class DeletingADraftTests(DeleteNotificationTestBase):

    def test_the_other_owner_is_told_in_app_and_by_email(self):
        record = self.co_owned(self.make_record())

        emails = self.delete_as_owner(record)

        [notice] = self.notices(self.reader, "Record Deleted")
        self.assertIn("deleted", notice["message"])
        self.assertIsNone(notice["record"])
        self.assertEqual(self.notices(self.owner, "Record Deleted"), [])
        self.assertEqual([recipients for recipients, _ in emails], [(self.reader.email,)])

    def test_a_sole_owner_s_delete_tells_no_one(self):
        record = self.make_record()

        emails = self.delete_as_owner(record)

        self.assertEqual(emails, [])
        for user in (self.owner, self.adviser, self.itso, self.rdco):
            with self.subTest(user=user.email):
                self.assertEqual(self.notices(user, "Record Deleted"), [])


# --- request_deletion -------------------------------------------------------------------

class RequestingDeletionTests(DeleteNotificationTestBase):

    def test_rdco_and_the_other_owner_are_told_with_a_link_and_by_email(self):
        record = self.co_owned(self.published())

        emails = self.delete_as_owner(record)

        [to_rdco] = self.notices(self.rdco, "Delete Request Submitted")
        self.assertEqual(to_rdco["record"], record.pk)
        self.assertIn("Delete Requests", to_rdco["message"])
        [to_owner] = self.notices(self.reader, "Delete Request Submitted")
        self.assertEqual(to_owner["record"], record.pk)
        self.assertEqual(self.notices(self.owner, "Delete Request Submitted"), [])
        self.assertEqual(self.notices(self.itso, "Delete Request Submitted"), [])

        rdco_emails = set(
            User.objects.filter(role__name=RoleName.RDCO, is_active=True).values_list("email", flat=True)
        )
        recipients = [set(r) for r, _ in emails]
        self.assertIn(rdco_emails, recipients)
        self.assertIn({self.reader.email}, recipients)
        self.assertEqual(len(recipients), 2)
