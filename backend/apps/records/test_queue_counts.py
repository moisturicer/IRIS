"""
`GET /dashboard/queue-counts/` (IR-1138): how many requests wait in RDCO's three
queues, so the sidebar can show a count beside each. RDCO only; any other
account is refused and nothing is counted for it.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, RoleRequest
from apps.records.models import DeleteRequest, DownloadRequest, Record, RecordOwner, RecordType
from apps.records.tests import make_user


class QueueCountsTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("qc_rdco@cit.edu", "RDCO")
        self.student = make_user("qc_student@cit.edu", "Student")
        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40,
            record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
            added_by=self.student, pipeline_status="published",
        )
        RecordOwner.objects.create(record=self.record, user=self.student, is_primary=True)

    def get(self, user):
        self.client.force_authenticate(user)
        return self.client.get(reverse("dashboard-queue-counts"))

    def test_an_empty_queue_counts_zero(self):
        response = self.get(self.rdco)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"download_requests": 0, "delete_requests": 0, "role_change_requests": 0},
        )

    def test_rdco_sees_only_what_is_pending(self):
        DownloadRequest.objects.create(record=self.record, requested_by=self.student)
        DownloadRequest.objects.create(record=self.record, requested_by=self.rdco)
        DownloadRequest.objects.create(record=self.record, requested_by=self.rdco, status="approved")
        DeleteRequest.objects.create(
            record=self.record, requested_by=self.student, previous_pipeline_status="published",
        )
        DeleteRequest.objects.create(
            record=self.record, requested_by=self.student, status="declined",
            previous_pipeline_status="published",
        )
        RoleRequest.objects.create(
            user=self.student, requested_role=Role.objects.get_or_create(name="Adviser")[0],
        )
        data = self.get(self.rdco).data
        self.assertEqual(data["download_requests"], 2)
        self.assertEqual(data["delete_requests"], 1)
        self.assertEqual(data["role_change_requests"], 1)

    def test_anyone_else_is_refused(self):
        DownloadRequest.objects.create(record=self.record, requested_by=self.student)
        self.assertEqual(self.get(self.student).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.get(make_user("qc_itso@cit.edu", "ITSO")).status_code, status.HTTP_403_FORBIDDEN)

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)
        response = self.client.get(reverse("dashboard-queue-counts"))
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class DeleteRequestStatusCountsTests(APITestCase):
    """`GET /records/delete-requests/counts/` (IR-1138): the count beside each tab."""

    def setUp(self):
        self.rdco = make_user("drc_rdco@cit.edu", "RDCO")
        self.student = make_user("drc_student@cit.edu", "Student")
        self.record = Record.objects.create(
            title="A" * 10, abstract="B" * 40,
            record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
            added_by=self.student, pipeline_status="published",
        )

    def make(self, state):
        DeleteRequest.objects.create(
            record=self.record, requested_by=self.student, status=state,
            previous_pipeline_status="published",
        )

    def counts(self, user):
        self.client.force_authenticate(user)
        return self.client.get(reverse("delete-requests-counts"))

    def test_counts_each_state_and_the_whole_queue(self):
        for state in ("pending", "pending", "approved", "declined", "declined", "declined"):
            self.make(state)
        response = self.counts(self.rdco)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"pending": 2, "approved": 1, "declined": 3, "all": 6})

    def test_an_empty_queue_is_all_zeros(self):
        self.assertEqual(self.counts(self.rdco).data, {"pending": 0, "approved": 0, "declined": 0, "all": 0})

    def test_anyone_else_is_refused(self):
        self.assertEqual(self.counts(self.student).status_code, status.HTTP_403_FORBIDDEN)

    def test_all_lists_every_state(self):
        for state in ("pending", "approved", "declined"):
            self.make(state)
        self.client.force_authenticate(self.rdco)
        response = self.client.get(reverse("delete-requests"), {"status": "all"})
        self.assertEqual(response.data["count"], 3)
