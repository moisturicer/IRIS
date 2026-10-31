"""
IR-674: RDCO alone decides a download request, through one rule on both routes.

`POST .../approve/` and `.../decline/` and `PATCH .../` used to be separate
copies of the decision, and only the POST routes told the requester. The
per-role refusal of other accounts is also in the authorization matrix
(`apps/tests/access/table.py`); these tests add the requester, the notification
and the routes agreeing with each other.

**Seam: the API.**
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.notifications.models import Notification
from apps.records.models import DownloadRequest, Record, RecordType
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName

DOWNLOAD_REQUESTS = "/api/v1/records/download-requests/"


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class DownloadRequestDecisionFixtures(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.requester = _user("dl-requester@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("dl-rdco@cit.edu", RoleName.RDCO)
        cls.other_rdco = _user("dl-rdco2@cit.edu", RoleName.RDCO)
        cls.record = Record.objects.create(
            title="A published thesis",
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            pipeline_status=PipelineStatus.PUBLISHED,
        )

    def pending(self, requested_by=None):
        return DownloadRequest.objects.create(
            record=self.record, requested_by=requested_by or self.requester,
        )

    def decide(self, route, request, user):
        self.client.force_authenticate(user)
        url = f"{DOWNLOAD_REQUESTS}{request.pk}/"
        if route == "patch-approve":
            return self.client.patch(url, {"action": "approve"}, format="json")
        if route == "patch-decline":
            return self.client.patch(url, {"action": "decline"}, format="json")
        return self.client.post(f"{url}{route}/", {}, format="json")


APPROVING = ("approve", "patch-approve")
DECLINING = ("decline", "patch-decline")


class OnlyRdcoDecidesTests(DownloadRequestDecisionFixtures):

    def test_the_other_offices_are_refused_and_nothing_changes(self):
        for role in (RoleName.ITSO, RoleName.IERC, RoleName.KTTO):
            office = _user(f"dl-{role.lower()}@cit.edu", role)
            for route in APPROVING + DECLINING:
                with self.subTest(role=role, route=route):
                    request = self.pending(requested_by=_user(f"{role}{route}@cit.edu", RoleName.STUDENT))
                    response = self.decide(route, request, office)
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                    request.refresh_from_db()
                    self.assertEqual(request.status, RequestStatus.PENDING)

    def test_a_student_cannot_decide_their_own_request(self):
        for route in APPROVING + DECLINING:
            with self.subTest(route=route):
                request = self.pending()
                self.assertEqual(
                    self.decide(route, request, self.requester).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                request.delete()

    def test_rdco_cannot_decide_their_own_request(self):
        for route in APPROVING + DECLINING:
            with self.subTest(route=route):
                request = self.pending(requested_by=self.rdco)
                response = self.decide(route, request, self.rdco)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                request.refresh_from_db()
                self.assertEqual(request.status, RequestStatus.PENDING)
                self.assertIsNone(request.reviewed_by)
                request.delete()

    def test_another_rdco_account_can_decide_an_rdco_request(self):
        request = self.pending(requested_by=self.rdco)
        response = self.decide("approve", request, self.other_rdco)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.APPROVED)


class BothRoutesApplyTheSameDecisionTests(DownloadRequestDecisionFixtures):

    def assert_decided(self, route, expected, notification_type):
        request = self.pending()
        response = self.decide(route, request, self.rdco)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        request.refresh_from_db()
        self.assertEqual(request.status, expected)
        self.assertEqual(request.reviewed_by, self.rdco)
        self.assertIsNotNone(request.reviewed_at)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.requester, notif_type__name=notification_type,
            ).count(),
            1,
        )
        request.delete()
        Notification.objects.all().delete()

    def test_each_approving_route_records_it_and_tells_the_requester(self):
        for route in APPROVING:
            with self.subTest(route=route):
                self.assert_decided(route, RequestStatus.APPROVED, "Download Request Approved")

    def test_each_declining_route_records_it_and_tells_the_requester(self):
        for route in DECLINING:
            with self.subTest(route=route):
                self.assert_decided(route, RequestStatus.DECLINED, "Download Request Declined")

    def test_a_decided_request_cannot_be_decided_again_on_either_route(self):
        for route in APPROVING + DECLINING:
            with self.subTest(route=route):
                request = self.pending()
                self.decide("decline", request, self.rdco)
                Notification.objects.all().delete()

                response = self.decide(route, request, self.other_rdco)

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                request.refresh_from_db()
                self.assertEqual(request.status, RequestStatus.DECLINED)
                self.assertEqual(request.reviewed_by, self.rdco)
                self.assertFalse(Notification.objects.exists())
                request.delete()


class ANewRequestNotifiesRdcoOnlyTests(DownloadRequestDecisionFixtures):

    def test_only_rdco_is_notified(self):
        self.client.force_authenticate(self.requester)

        response = self.client.post(DOWNLOAD_REQUESTS, {"record": self.record.pk}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        broadcasts = Notification.objects.filter(
            notif_type__name="Download Request Submitted",
        ).values_list("broadcast_to_role__name", flat=True)
        self.assertEqual(list(broadcasts), [RoleName.RDCO])
