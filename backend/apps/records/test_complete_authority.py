"""
IR-267: the assigned Adviser can complete an approved Proposal.

ADR-021 §3 gives a Proposal's decision to "the assigned Adviser OR RDCO", and
the same two parties complete it (`approved` -> `completed`). Until this change
only RDCO could.

**Two layers refuse, and the expected code says which.** A role that can never
complete -- a student, ITSO, IERC, KTTO -- is refused by the permission class
with **403** before the record is looked up, so the answer says nothing about
the record. An Adviser passes that gate, but their queryset for this action is
narrowed to the records they advise, so an Adviser who is *not* assigned gets
**404** -- identical to a record that does not exist. That matters here because
an approved Proposal is publicly readable today, so the unassigned Adviser can
open it; the 404 is about completing it, not about seeing it.

**Intake is not a separate case yet.** Intake is staffed by the RDCO role, and
until the party model lands (IR-256 onward) nothing on a request distinguishes
"RDCO at intake" from "RDCO deciding". The RDCO cases below therefore cover
both; a separate Intake refusal has nothing to key on in the current pipeline.

**Seam: the records API.** A refusal is asserted in three halves -- the request
fails, the Record did not move, and nobody was notified. Email is patched at
`send_email_async`, the boundary the notification service sends through.
"""

from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.notifications.models import Notification
from apps.records.models import Record, RecordOwner, RecordType
from core.enums import PipelineStatus, RecordTypeName, RoleName

SEND_EMAIL = "apps.notifications.services.send_email_async"


def _user(email, role_name):
    # Roles are seeded by migration with explicit keys; create() would collide.
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class CompleteAuthorityTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("complete-owner@cit.edu", RoleName.STUDENT)
        cls.other_student = _user("complete-student@cit.edu", RoleName.STUDENT)
        cls.adviser = _user("complete-adviser@cit.edu", RoleName.ADVISER)
        cls.other_adviser = _user("complete-other-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = _user("complete-rdco@cit.edu", RoleName.RDCO)
        cls.offices = {
            "itso": _user("complete-itso@cit.edu", RoleName.ITSO),
            "ierc": _user("complete-ierc@cit.edu", RoleName.IERC),
            "ktto": _user("complete-ktto@cit.edu", RoleName.KTTO),
        }

    # --- setup ---------------------------------------------------------------

    def make_record(
        self,
        type_name=RecordTypeName.PROPOSAL,
        pipeline_status=PipelineStatus.APPROVED,
    ):
        record = Record.objects.create(
            title=f"Complete authority {type_name}",
            abstract="A" * 40,
            record_type=RecordType.objects.get(name=type_name),
            added_by=self.owner,
            adviser=self.adviser,
            pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    # --- drivers and observations --------------------------------------------

    def complete(self, record_pk, actor):
        self.client.force_authenticate(actor)
        with mock.patch(SEND_EMAIL) as send_email:
            response = self.client.post(reverse("record-complete", args=[record_pk]))
        return response, send_email

    def status_of(self, record):
        record.refresh_from_db()
        return record.pipeline_status

    def owner_notifications(self, record):
        return Notification.objects.filter(record=record, recipient=self.owner)

    def assert_completed_and_owner_told(self, record, actor):
        response, send_email = self.complete(record.pk, actor)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.COMPLETED)
        self.assertEqual(self.owner_notifications(record).count(), 1)
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.kwargs["recipient_list"], [self.owner.email])
        return self.owner_notifications(record).get()

    def assert_refused_without_effect(self, record, actor, expected_code):
        response, send_email = self.complete(record.pk, actor)

        self.assertEqual(response.status_code, expected_code, response.data)
        self.assertEqual(self.status_of(record), PipelineStatus.APPROVED)
        self.assertFalse(self.owner_notifications(record).exists())
        send_email.assert_not_called()

    # --- the two parties who may complete ------------------------------------

    def test_the_assigned_adviser_completes_an_approved_proposal(self):
        record = self.make_record()
        notification = self.assert_completed_and_owner_told(record, self.adviser)
        # The owner is told who did it. The message used to say "by RDCO"
        # unconditionally, which would be false for an Adviser completion.
        self.assertNotIn("RDCO", notification.message)
        self.assertIn("Adviser", notification.message)

    def test_rdco_still_completes_an_approved_proposal(self):
        record = self.make_record()
        notification = self.assert_completed_and_owner_told(record, self.rdco)
        self.assertIn("RDCO", notification.message)

    # --- everyone else --------------------------------------------------------

    def test_an_unassigned_adviser_is_refused_with_404(self):
        record = self.make_record()
        self.assert_refused_without_effect(
            record, self.other_adviser, status.HTTP_404_NOT_FOUND
        )

    def test_the_unassigned_advisers_404_is_the_missing_record_response(self):
        """
        "Not yours" and "does not exist" must be indistinguishable, so the
        refusal cannot be used to confirm the record is a Proposal awaiting
        completion.
        """
        record = self.make_record()
        missing_pk = 999_999_999
        self.assertFalse(Record.objects.filter(pk=missing_pk).exists())

        refused, _ = self.complete(record.pk, self.other_adviser)
        missing, _ = self.complete(missing_pk, self.other_adviser)

        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(refused.data, missing.data)

    def test_offices_are_refused(self):
        for name, office_user in self.offices.items():
            with self.subTest(office=name):
                record = self.make_record()
                self.assert_refused_without_effect(
                    record, office_user, status.HTTP_403_FORBIDDEN
                )

    def test_students_are_refused_including_the_owner(self):
        for label, student in (("owner", self.owner), ("other", self.other_student)):
            with self.subTest(student=label):
                record = self.make_record()
                self.assert_refused_without_effect(
                    record, student, status.HTTP_403_FORBIDDEN
                )

    # --- the preconditions bind the Adviser too --------------------------------

    def test_the_assigned_adviser_cannot_complete_off_the_proposal_route(self):
        cases = [
            ("not yet approved", RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW),
            ("already completed", RecordTypeName.PROPOSAL, PipelineStatus.COMPLETED),
            ("not a proposal", RecordTypeName.THESIS_RESEARCH, PipelineStatus.APPROVED),
        ]
        for label, type_name, pipeline_status in cases:
            with self.subTest(case=label):
                record = self.make_record(type_name, pipeline_status)
                response, send_email = self.complete(record.pk, self.adviser)
                self.assertEqual(
                    response.status_code, status.HTTP_400_BAD_REQUEST, response.data
                )
                self.assertEqual(self.status_of(record), pipeline_status)
                send_email.assert_not_called()
