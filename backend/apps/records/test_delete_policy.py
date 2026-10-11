"""
Who may delete a record, and what a delete does in each state (IR-508, ADR-032
§10 Amendment of 2026-10-11).

Until IR-508 `DELETE /records/<id>/` was `IsOwnerOrStaff`: any office could
soft-delete a student's draft outright, or file a delete request on accepted
work with the office member recorded as the requester. A second delete on a
record already awaiting RDCO's decision soft-deleted it outright, skipping the
decision. Settled with the project lead:

1. only an owner deletes -- any owner, never an office or the Adviser;
2. each status keeps its act -- a draft or rejected record goes now, a record
   in review goes now and its review is withdrawn (IR-274), accepted work
   becomes a delete request for RDCO -- and `pending_delete` is refused (400);
3. Record detail names the act: `delete_record`, `withdraw_submission` or
   `request_deletion`, offered to owners only.

Refusals follow ADR-022 §Amendment 4: 403 for a record the caller can see.
"""

from django.urls import reverse
from rest_framework import status

from apps.records.models import DeleteRequest, Record, RecordOwner
from apps.reviews.test_decisions import DecisionTestBase
from core.enums import PipelineStatus, RequestStatus

DELETE_KEYS = {"delete_record", "withdraw_submission", "request_deletion"}


def detail_url(record):
    return reverse("record-detail", args=[record.pk])


class DeletePolicyTestBase(DecisionTestBase):

    def delete(self, record, as_user):
        self.client.force_authenticate(as_user)
        return self.client.delete(detail_url(record))

    def stored(self, record):
        return Record.objects.with_deleted().get(pk=record.pk)

    def published(self):
        record = self.at_adviser()
        self.decided(record, self.adviser, "publish")
        return record

    def rejected(self):
        record = self.make_record()
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.REJECTED)
        record.refresh_from_db()
        return record

    def offered(self, record, as_user):
        return set(self.detail(record, as_user)["capabilities"]) & DELETE_KEYS


# --- who ------------------------------------------------------------------------------

class OnlyAnOwnerDeletesTests(DeletePolicyTestBase):

    def test_no_office_deletes_or_requests_deletion_of_a_record_that_is_not_theirs(self):
        """A draft, a record in review, a published one: every office can see all three."""
        for state in ("make_record", "at_adviser", "published"):
            record = getattr(self, state)()
            before = record.pipeline_status
            for office in (self.itso, self.ierc, self.rdco):
                with self.subTest(state=state, office=office.email):
                    response = self.delete(record, office)

                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
                    stored = self.stored(record)
                    self.assertFalse(stored.is_deleted)
                    self.assertEqual(stored.pipeline_status, before)
            self.assertFalse(DeleteRequest.objects.filter(record=record).exists())

    def test_the_adviser_does_not_delete_the_record_they_review(self):
        record = self.at_adviser()

        response = self.delete(record, self.adviser)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
        self.assertFalse(self.stored(record).is_deleted)

    def test_someone_who_cannot_see_the_record_gets_404(self):
        record = self.make_record()

        response = self.delete(record, self.stranger)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(self.stored(record).is_deleted)

    def test_any_owner_may_request_deletion_and_is_the_requester(self):
        record = self.published()
        RecordOwner.objects.create(record=record, user=self.reader, is_primary=False)

        response = self.delete(record, self.reader)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(DeleteRequest.objects.get(record=record).requested_by, self.reader)


# --- what, by state -------------------------------------------------------------------

class WhatADeleteDoesTests(DeletePolicyTestBase):

    def test_a_draft_or_rejected_record_is_gone_now(self):
        for state in ("make_record", "rejected"):
            with self.subTest(state=state):
                record = getattr(self, state)()

                response = self.delete(record, self.owner)

                self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
                self.assertTrue(self.stored(record).is_deleted)
                self.assertFalse(DeleteRequest.objects.filter(record=record).exists())

    def test_accepted_work_waits_for_rdco(self):
        record = self.published()

        response = self.delete(record, self.owner)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        stored = self.stored(record)
        self.assertFalse(stored.is_deleted)
        self.assertEqual(stored.pipeline_status, PipelineStatus.PENDING_DELETE)
        self.assertEqual(DeleteRequest.objects.get(record=record).status, RequestStatus.PENDING)

    def test_a_second_delete_does_not_skip_rdco_s_decision(self):
        """The bypass IR-508 closes: a soft delete is legal from every status."""
        record = self.published()
        self.assertEqual(self.delete(record, self.owner).status_code, status.HTTP_204_NO_CONTENT)

        response = self.delete(record, self.owner)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("already pending", response.data["detail"])
        stored = self.stored(record)
        self.assertFalse(stored.is_deleted)
        self.assertEqual(stored.pipeline_status, PipelineStatus.PENDING_DELETE)
        self.assertEqual(
            list(DeleteRequest.objects.filter(record=record).values_list("status", flat=True)),
            [RequestStatus.PENDING],
        )


# --- what Record detail offers ----------------------------------------------------------

class TheOfferNamesTheActTests(DeletePolicyTestBase):

    def test_an_owner_is_offered_the_one_act_its_status_names(self):
        cases = (
            ("make_record", {"delete_record"}),
            ("rejected", {"delete_record"}),
            ("at_adviser", {"withdraw_submission"}),
            ("published", {"request_deletion"}),
        )
        for state, expected in cases:
            with self.subTest(state=state):
                self.assertEqual(self.offered(getattr(self, state)(), self.owner), expected)

    def test_nothing_is_offered_while_a_decision_is_pending(self):
        record = self.published()
        self.delete(record, self.owner)

        self.assertEqual(self.offered(record, self.owner), set())

    def test_no_office_and_not_the_adviser_is_offered_any(self):
        record = self.at_adviser()
        for user in (self.itso, self.rdco, self.adviser):
            with self.subTest(user=user.email):
                self.assertEqual(self.offered(record, user), set())
