"""
The Proposal *complete* act is retired (IR-271, ADR-032 §2).

**History.** IR-267 let the assigned Adviser, as well as RDCO, mark an approved
Proposal completed (`approved` -> `completed`, ADR-021 §3). ADR-032 §2 retired
the act: "research finished" now lives in the Thesis or Project the Proposal
continues as (§6), so `approved` -- shown as *Accepted* -- is a Proposal's
resting state, and nothing new writes `completed`. IR-271 retires it for
**every** Proposal, legacy ones included, as the ADR says, rather than only for
the new model as its card first read (Jira comment 10589).

**The two refusal layers IR-267 built still answer first.** A role that could
never complete -- a student, ITSO, IERC, KTTO -- is refused by the permission
class with **403** before the record is looked up. An Adviser passes that gate,
but their queryset for this action is narrowed to the records they advise, so
an unassigned Adviser gets **404**, identical to a record that does not exist.
Only a caller who could once have completed reaches the act itself, which now
refuses with **400**, saying it is retired.

**IR-267's carried criterion, "Intake cannot complete", is dropped, not
untested.** It stood here as a documented gap: Intake was staffed by the RDCO
role, so nothing on a request told "RDCO at intake" from "RDCO deciding". Both
halves are gone -- intake is retired (ADR-032 §1) and so is complete -- so
there is no Intake completion left to refuse separately (IR-271).

**An existing `completed` Proposal keeps its value** and still reads as
*Completed*.

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


class CompleteRetiredTests(APITestCase):

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

    def assert_refused_without_effect(self, record, actor, expected_code):
        before = record.pipeline_status
        response, send_email = self.complete(record.pk, actor)

        self.assertEqual(response.status_code, expected_code, response.data)
        self.assertEqual(self.status_of(record), before)
        self.assertFalse(Notification.objects.filter(record=record).exists())
        send_email.assert_not_called()
        return response

    # --- the two parties who once could complete are now refused -------------

    def test_the_assigned_adviser_can_no_longer_complete_an_accepted_proposal(self):
        record = self.make_record()
        response = self.assert_refused_without_effect(
            record, self.adviser, status.HTTP_400_BAD_REQUEST
        )
        self.assertIn("retired", response.data["detail"])

    def test_rdco_can_no_longer_complete_one_either(self):
        record = self.make_record()
        response = self.assert_refused_without_effect(
            record, self.rdco, status.HTTP_400_BAD_REQUEST
        )
        self.assertIn("retired", response.data["detail"])

    def test_off_the_old_route_it_is_refused_the_same_way(self):
        cases = [
            ("not yet approved", RecordTypeName.PROPOSAL, PipelineStatus.ADVISER_REVIEW),
            ("already completed", RecordTypeName.PROPOSAL, PipelineStatus.COMPLETED),
            ("not a proposal", RecordTypeName.THESIS_RESEARCH, PipelineStatus.APPROVED),
        ]
        for label, type_name, pipeline_status in cases:
            with self.subTest(case=label):
                record = self.make_record(type_name, pipeline_status)
                self.assert_refused_without_effect(
                    record, self.adviser, status.HTTP_400_BAD_REQUEST
                )

    # --- the earlier layers still answer first --------------------------------

    def test_an_unassigned_adviser_is_refused_with_404(self):
        record = self.make_record()
        self.assert_refused_without_effect(
            record, self.other_adviser, status.HTTP_404_NOT_FOUND
        )

    def test_the_unassigned_advisers_404_is_the_missing_record_response(self):
        """"Not yours" and "does not exist" stay indistinguishable."""
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

    # --- what already exists keeps reading correctly -------------------------

    def test_an_existing_completed_proposal_still_reads_as_completed(self):
        record = self.make_record(pipeline_status=PipelineStatus.COMPLETED)
        self.client.force_authenticate(self.owner)
        detail = self.client.get(reverse("record-detail", args=[record.pk])).data
        self.assertEqual(detail["pipeline_status"], PipelineStatus.COMPLETED)
        self.assertEqual(detail["workflow_state_label"], "Completed")

    def test_an_accepted_proposal_reads_as_accepted(self):
        record = self.make_record()
        self.client.force_authenticate(self.owner)
        detail = self.client.get(reverse("record-detail", args=[record.pk])).data
        self.assertEqual(detail["workflow_state_label"], "Accepted")
