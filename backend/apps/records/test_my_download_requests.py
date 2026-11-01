"""
IR-743: the reader's own download requests, for My Library's "Download
requests" view (ADR-048). Only the reader's own requests are listed, newest
first; the server says each one's state and what the reader may do about it,
so the browser never decides access itself.

**Seam: the API.**
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.records.models import DownloadRequest, Record, RecordType
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName

MINE = "/api/v1/records/download-requests/mine/"
WHY = "I am citing its survey method in my own thesis."


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


def _record(title, pipeline_status=PipelineStatus.PUBLISHED):
    return Record.objects.create(
        title=title,
        record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
        pipeline_status=pipeline_status,
    )


class MyDownloadRequestsTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.reader = _user("mine-reader@cit.edu", RoleName.STUDENT)
        cls.stranger = _user("mine-stranger@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("mine-rdco@cit.edu", RoleName.RDCO)
        cls.record = _record("A published thesis")
        cls.other_record = _record("Another published thesis")

    def ask(self, record=None, user=None, *, days_ago=0, **fields):
        request = DownloadRequest.objects.create(
            record=record or self.record, requested_by=user or self.reader, note=WHY, **fields,
        )
        # `created_at` is auto_now_add; age it to fix the order.
        DownloadRequest.objects.filter(pk=request.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago),
        )
        return request

    def decided(self, outcome, *, days_ago=0, record=None, **fields):
        return self.ask(
            record, days_ago=days_ago, status=outcome, reviewed_by=self.rdco,
            reviewed_at=timezone.now() - timedelta(days=days_ago), **fields,
        )

    def granted(self, *, expires_in_days, **kwargs):
        return self.decided(
            RequestStatus.APPROVED,
            grant_expires_at=timezone.now() + timedelta(days=expires_in_days), **kwargs,
        )

    def mine(self, user=None):
        self.client.force_authenticate(user or self.reader)
        response = self.client.get(MINE)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_lists_only_the_readers_own_requests_newest_first(self):
        older = self.ask(self.other_record, days_ago=3)
        newer = self.ask(days_ago=1)
        self.ask(user=self.stranger)

        rows = self.mine()

        self.assertEqual([row["id"] for row in rows], [newer.pk, older.pk])
        self.assertEqual(rows[0]["record"], self.record.pk)
        self.assertEqual(rows[0]["record_title"], "A published thesis")
        self.assertEqual(rows[0]["note"], WHY)
        self.assertIn("created_at", rows[0])

    def test_names_no_one_else_and_no_reviewer(self):
        self.ask()
        row = self.mine()[0]
        for leaked in ("requested_by", "requested_by_name", "requested_by_email", "reviewed_by", "revoked_by"):
            self.assertNotIn(leaked, row)

    def test_another_readers_request_is_invisible_whatever_their_role(self):
        self.ask(user=self.stranger)
        self.assertEqual(self.mine(), [])
        # Not even RDCO sees another reader's request through this list.
        self.assertEqual(self.mine(self.rdco), [])

    def test_a_cancelled_request_is_left_out(self):
        self.ask(status=RequestStatus.CANCELLED, cancelled_at=timezone.now())
        self.assertEqual(self.mine(), [])

    def test_a_request_on_a_record_the_reader_can_no_longer_read_is_left_out(self):
        withdrawn = _record("Since withdrawn", PipelineStatus.DRAFT)
        self.ask(withdrawn)
        self.assertEqual(self.mine(), [])

    def test_each_state_and_what_it_offers(self):
        cases = [
            ("pending", self.ask(_record("P"), days_ago=1), ["cancel"]),
            ("granted", self.granted(expires_in_days=5, record=_record("G"), days_ago=2), ["download"]),
            ("expired", self.granted(expires_in_days=-1, record=_record("E"), days_ago=3), ["request_again"]),
            ("declined", self.decided(
                RequestStatus.DECLINED, record=_record("D"), days_ago=4, rdco_note="Not for this purpose.",
            ), ["request_again"]),
            ("revoked", self.granted(
                expires_in_days=5, record=_record("R"), days_ago=5,
            ), ["request_again"]),
        ]
        revoked = cases[-1][1]
        DownloadRequest.objects.filter(pk=revoked.pk).update(
            status=RequestStatus.REVOKED, revoked_at=timezone.now(), rdco_note="Misused.",
        )

        rows = {row["id"]: row for row in self.mine()}

        for state, request, actions in cases:
            with self.subTest(state=state):
                self.assertEqual(rows[request.pk]["state"], state)
                self.assertEqual(rows[request.pk]["actions"], actions)
        granted = rows[cases[1][1].pk]
        self.assertIsNotNone(granted["grant_expires_at"])
        self.assertEqual(rows[cases[3][1].pk]["rdco_note"], "Not for this purpose.")
        self.assertEqual(rows[revoked.pk]["rdco_note"], "Misused.")
        # Only a decline or a revocation carries RDCO's note.
        self.assertEqual(rows[cases[0][1].pk]["rdco_note"], "")
        # Only a live grant says until when.
        self.assertIsNone(rows[cases[2][1].pk]["grant_expires_at"])

    def test_request_again_only_on_the_request_that_counts(self):
        declined = self.decided(RequestStatus.DECLINED, days_ago=5, rdco_note="No.")
        pending = self.ask(days_ago=1)

        rows = {row["id"]: row for row in self.mine()}

        # Asked again since: the old decline is history, the new one is cancellable.
        self.assertEqual(rows[declined.pk]["state"], "declined")
        self.assertEqual(rows[declined.pk]["actions"], [])
        self.assertEqual(rows[pending.pk]["actions"], ["cancel"])

    def test_a_cancelled_newer_request_does_not_hide_request_again(self):
        declined = self.decided(RequestStatus.DECLINED, days_ago=5, rdco_note="No.")
        self.ask(days_ago=1, status=RequestStatus.CANCELLED, cancelled_at=timezone.now())

        rows = self.mine()

        self.assertEqual([row["id"] for row in rows], [declined.pk])
        self.assertEqual(rows[0]["actions"], ["request_again"])

    def test_anonymous_is_refused(self):
        self.assertIn(
            self.client.get(MINE).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
