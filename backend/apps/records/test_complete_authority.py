"""
The Proposal *complete* act is gone (IR-271 retired it, IR-274 removed it).

**History.** IR-267 let the assigned Adviser, as well as RDCO, mark an approved
Proposal completed (`approved` -> `completed`, ADR-021 §3). ADR-032 §2 retired
the act: "research finished" now lives in the Thesis or Project the Proposal
continues as (§6), so `approved` -- shown as *Accepted* -- is a Proposal's
resting state. IR-271 made `/records/<id>/complete/` refuse every record;
IR-274 deleted the route and both of IR-267's authority checks with it. RDCO
keeps a Thesis or Project unlisted through the decide action (IR-270).

**An existing `completed` Proposal keeps its value** and still reads as
*Completed*.
"""

from unittest import mock

from django.urls import NoReverseMatch, reverse
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


class CompleteRemovedTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("complete-owner@cit.edu", RoleName.STUDENT)
        cls.adviser = _user("complete-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = _user("complete-rdco@cit.edu", RoleName.RDCO)

    def make_record(self, pipeline_status=PipelineStatus.APPROVED):
        record = Record.objects.create(
            title="Complete removed",
            abstract="A" * 40,
            record_type=RecordType.objects.get(name=RecordTypeName.PROPOSAL),
            added_by=self.owner,
            adviser=self.adviser,
            pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    def test_the_route_no_longer_exists(self):
        with self.assertRaises(NoReverseMatch):
            reverse("record-complete", args=[1])

    def test_posting_to_the_old_url_finds_nothing_and_changes_nothing(self):
        record = self.make_record()
        url = reverse("record-detail", args=[record.pk]) + "complete/"
        for actor in (self.adviser, self.rdco):
            with self.subTest(actor=actor.email), mock.patch(SEND_EMAIL) as send_email:
                self.client.force_authenticate(actor)
                response = self.client.post(url)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                record.refresh_from_db()
                self.assertEqual(record.pipeline_status, PipelineStatus.APPROVED)
                self.assertFalse(Notification.objects.filter(record=record).exists())
                send_email.assert_not_called()

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
