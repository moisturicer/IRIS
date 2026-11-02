"""
IR-677: the record detail says where the viewer's download stands.

The paper page shows Download, Request download, Request pending, or Request
again from this block alone, so the browser never decides access itself. It is
`download_access` (IR-675) in words: the same answer the download route gives.

**Seam: the API.**
"""

from django.utils.dateparse import parse_datetime
from rest_framework import status

from apps.records.models import DownloadRequest
from apps.records.test_download_grant import Fixtures, _user
from core.enums import RequestStatus, RoleName


class DownloadStateTests(Fixtures):

    def block(self, user=None):
        self.client.force_authenticate(user or self.reader)
        response = self.client.get(f"/api/v1/records/{self.record.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.data["download"]

    def assert_state(self, block, state, *, allowed):
        self.assertEqual(block["state"], state)
        self.assertIs(block["allowed"], allowed)
        self.assertTrue(block["message"].strip(), "every state is explained in the server's words")

    def test_an_exempt_reader_may_download(self):
        for user in (self.owner, self.adviser, _user("state-rdco@cit.edu", RoleName.RDCO)):
            with self.subTest(user=user.email):
                block = self.block(user)
                self.assert_state(block, "exempt", allowed=True)
                self.assertIsNone(block["grant_expires_at"])

    def test_no_request_offers_a_request(self):
        self.assert_state(self.block(), "none", allowed=False)

    def test_a_pending_request_names_itself(self):
        pending = self.request_by(state=RequestStatus.PENDING, expires_in=None)
        block = self.block()
        self.assert_state(block, "pending", allowed=False)
        self.assertEqual(block["request"], pending.pk)

    def test_a_live_grant_says_until_when(self):
        grant = self.request_by()
        block = self.block()
        self.assert_state(block, "granted", allowed=True)
        self.assertEqual(parse_datetime(block["grant_expires_at"]), grant.grant_expires_at)
        self.assertEqual(block["request"], grant.pk)

    def test_each_ended_request_is_its_own_state(self):
        cases = {
            "declined": dict(state=RequestStatus.DECLINED, expires_in=None),
            "revoked": dict(state=RequestStatus.REVOKED),
            "expired": dict(state=RequestStatus.APPROVED, expires_in=-1),
        }
        for expected, kwargs in cases.items():
            with self.subTest(state=expected):
                DownloadRequest.objects.filter(record=self.record).delete()
                self.request_by(**kwargs)
                self.assert_state(self.block(), expected, allowed=False)

    def test_the_block_agrees_with_the_download_route(self):
        """Whatever the block says, the route does: allowed is served, refused is a 403."""
        self.request_by(state=RequestStatus.PENDING, expires_in=None)
        self.assertFalse(self.block()["allowed"])
        self.assertEqual(self.get().status_code, status.HTTP_403_FORBIDDEN)

        self.assertTrue(self.block(self.owner)["allowed"])
        self.assertEqual(self.get(self.owner).status_code, status.HTTP_200_OK)

    def test_another_readers_request_is_never_disclosed(self):
        other = _user("state-other@cit.edu")
        self.request_by(user=other)
        block = self.block()
        self.assert_state(block, "none", allowed=False)
        self.assertIsNone(block["request"])
