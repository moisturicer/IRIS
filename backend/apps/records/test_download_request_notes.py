"""
IR-688: a download request carries the reader's note, a decline or a revocation
carries RDCO's, the reader may cancel a pending request, and RDCO may revoke a
live grant (ADR-048, decisions 3, 4 and 6).

The per-role refusals of accounts with no claim are also in the authorization
matrix (`apps/tests/access/table.py`); these tests add each state.

**Seam: the API.**
"""

from datetime import timedelta
from unittest import mock

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.records.models import DownloadRequest, Record, RecordType
from core.enums import PipelineStatus, RecordTypeName, RequestStatus, RoleName

DOWNLOAD_REQUESTS = "/api/v1/records/download-requests/"
WHY = "I am citing its survey method in my own thesis."


def _user(email, role_name):
    role = Role.objects.get_or_create(name=role_name)[0]
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test",
        last_name="User", role=role, is_verified=True,
    )


class Fixtures(APITestCase):
    """Email is captured at `send_email_async`: the broker is a real queue."""

    def setUp(self):
        patcher = mock.patch("apps.notifications.services.send_email_async")
        self.send_email = patcher.start()
        self.addCleanup(patcher.stop)

    def emails(self):
        return [call.kwargs for call in self.send_email.call_args_list]

    @classmethod
    def setUpTestData(cls):
        cls.reader = _user("notes-reader@cit.edu", RoleName.STUDENT)
        cls.stranger = _user("notes-stranger@cit.edu", RoleName.STUDENT)
        cls.rdco = _user("notes-rdco@cit.edu", RoleName.RDCO)
        cls.itso = _user("notes-itso@cit.edu", RoleName.ITSO)
        cls.record = Record.objects.create(
            title="A published thesis",
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            pipeline_status=PipelineStatus.PUBLISHED,
        )

    def ask(self, user=None, **data):
        self.client.force_authenticate(user or self.reader)
        return self.client.post(DOWNLOAD_REQUESTS, {"record": self.record.pk, **data}, format="json")

    def act(self, user, request, route, **data):
        self.client.force_authenticate(user)
        return self.client.post(f"{DOWNLOAD_REQUESTS}{request.pk}/{route}/", data, format="json")

    def pending(self, **fields):
        return DownloadRequest.objects.create(record=self.record, requested_by=self.reader, note=WHY, **fields)

    def granted(self, *, days=30):
        now = timezone.now()
        return self.pending(
            status=RequestStatus.APPROVED, reviewed_by=self.rdco, reviewed_at=now,
            grant_expires_at=now + timedelta(days=days),
        )

    def state(self):
        self.client.force_authenticate(self.reader)
        return self.client.get(f"/api/v1/records/{self.record.pk}/").data["download"]


class TheReadersNoteTests(Fixtures):

    def test_a_request_needs_a_note(self):
        for data in ({}, {"note": ""}, {"note": "   "}):
            with self.subTest(data=data):
                response = self.ask(**data)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("note", response.data)
        self.assertFalse(DownloadRequest.objects.exists())

    def test_a_note_over_500_characters_is_refused(self):
        self.assertEqual(self.ask(note="x" * 501).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.ask(note="x" * 500).status_code, status.HTTP_201_CREATED)

    def test_the_note_is_stored_and_shown_in_rdcos_queue(self):
        self.assertEqual(self.ask(note=f"  {WHY}  ").status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(self.rdco)
        queue = self.client.get(DOWNLOAD_REQUESTS).data["results"]
        self.assertEqual([row["note"] for row in queue], [WHY])


class TheDeclineNoteTests(Fixtures):

    def test_declining_needs_a_note_on_both_routes(self):
        request = self.pending()
        self.client.force_authenticate(self.rdco)
        url = f"{DOWNLOAD_REQUESTS}{request.pk}/"
        for response in (
            self.client.post(f"{url}decline/", {}, format="json"),
            self.client.post(f"{url}decline/", {"note": "  "}, format="json"),
            self.client.post(f"{url}decline/", {"note": "x" * 501}, format="json"),
            self.client.patch(url, {"action": "decline"}, format="json"),
        ):
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("note", response.data)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.PENDING)

    def test_the_decline_note_reaches_the_reader_in_app_by_email_and_on_the_paper_page(self):
        request = self.pending()
        response = self.act(self.rdco, request, "decline", note="Ask your adviser to request it.")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        request.refresh_from_db()
        self.assertEqual(request.rdco_note, "Ask your adviser to request it.")
        notice = Notification.objects.get(recipient=self.reader)
        self.assertIn("Ask your adviser to request it.", notice.message)
        [email] = self.emails()
        self.assertEqual(email["recipient_list"], [self.reader.email])
        self.assertIn("Ask your adviser to request it.", email["message"])
        self.assertIn(f"/records/{self.record.pk}", email["message"])
        self.assertNotIn("/download/", email["message"])

        block = self.state()
        self.assertEqual((block["state"], block["rdco_note"]), ("declined", "Ask your adviser to request it."))

    def test_approving_takes_no_note(self):
        request = self.pending()
        self.assertEqual(self.act(self.rdco, request, "approve").status_code, status.HTTP_200_OK)
        request.refresh_from_db()
        self.assertEqual((request.status, request.rdco_note), (RequestStatus.APPROVED, ""))

    def test_a_decline_from_before_notes_has_an_empty_note(self):
        self.pending(status=RequestStatus.DECLINED, reviewed_by=self.rdco, reviewed_at=timezone.now())
        block = self.state()
        self.assertEqual((block["state"], block["rdco_note"]), ("declined", ""))


class CancelTests(Fixtures):

    def test_the_requester_cancels_a_pending_request_and_may_ask_again(self):
        request = self.pending()
        response = self.act(self.reader, request, "cancel")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], RequestStatus.CANCELLED)

        self.client.force_authenticate(self.rdco)
        self.assertEqual(self.client.get(DOWNLOAD_REQUESTS, {"status": "pending"}).data["results"], [])
        self.assertEqual(self.state()["state"], "none")
        self.assertEqual(self.ask(note=WHY).status_code, status.HTTP_201_CREATED)

        event = AuditEvent.objects.get(event_type=AuditEvent.DOWNLOAD_REQUEST_CANCELLED)
        self.assertEqual(
            (event.user, event.record, event.metadata), (self.reader, self.record, {"request": request.pk}),
        )
        self.assertFalse(Notification.objects.filter(recipient=self.reader).exists())

    def test_only_the_requester_may_cancel_and_others_see_no_such_request(self):
        request = self.pending()
        for user in (self.stranger, self.rdco, self.itso):
            with self.subTest(user=user.email):
                self.assertEqual(self.act(user, request, "cancel").status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(None)
        self.assertEqual(
            self.client.post(f"{DOWNLOAD_REQUESTS}{request.pk}/cancel/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.PENDING)

    def test_only_a_pending_request_can_be_cancelled(self):
        for state in (
            RequestStatus.APPROVED, RequestStatus.DECLINED, RequestStatus.REVOKED, RequestStatus.CANCELLED,
        ):
            with self.subTest(state=state):
                request = self.pending(status=state)
                self.assertEqual(self.act(self.reader, request, "cancel").status_code, status.HTTP_400_BAD_REQUEST)
                request.refresh_from_db()
                self.assertEqual(request.status, state)
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.DOWNLOAD_REQUEST_CANCELLED).exists())


class RevokeTests(Fixtures):

    def download(self):
        self.client.force_authenticate(self.reader)
        return self.client.get(f"/api/v1/records/{self.record.pk}/download/")

    def test_rdco_revokes_a_live_grant_with_a_note(self):
        grant = self.granted()
        self.assertTrue(self.state()["allowed"])

        response = self.act(self.rdco, grant, "revoke", note="Shared outside CIT-U.")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual((response.data["status"], response.data["rdco_note"]), ("revoked", "Shared outside CIT-U."))

        refused = self.download()
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refused.json()["code"], "request_revoked")
        block = self.state()
        self.assertEqual((block["state"], block["rdco_note"]), ("revoked", "Shared outside CIT-U."))

        notice = Notification.objects.get(recipient=self.reader)
        self.assertIn("Shared outside CIT-U.", notice.message)
        [email] = self.emails()
        self.assertEqual(email["recipient_list"], [self.reader.email])
        self.assertIn("Shared outside CIT-U.", email["message"])
        self.assertIn(f"/records/{self.record.pk}", email["message"])
        self.assertNotIn("/download/", email["message"])

        event = AuditEvent.objects.get(event_type=AuditEvent.DOWNLOAD_GRANT_REVOKED)
        self.assertEqual(
            (event.user, event.record, event.metadata),
            (self.rdco, self.record, {"request": grant.pk, "requested_by": self.reader.pk}),
        )
        self.assertEqual(self.ask(note=WHY).status_code, status.HTTP_201_CREATED)

    def test_the_approval_is_kept_beside_the_revocation(self):
        grant = self.granted()
        self.act(self.rdco, grant, "revoke", note="Given by mistake.")
        grant.refresh_from_db()
        self.assertEqual((grant.reviewed_by, grant.revoked_by), (self.rdco, self.rdco))
        self.assertIsNotNone(grant.reviewed_at)
        self.assertIsNotNone(grant.revoked_at)

    def test_revoking_needs_a_note(self):
        grant = self.granted()
        for data in ({}, {"note": " "}, {"note": "x" * 501}):
            with self.subTest(data=data):
                response = self.act(self.rdco, grant, "revoke", **data)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("note", response.data)
        grant.refresh_from_db()
        self.assertEqual(grant.status, RequestStatus.APPROVED)

    def test_only_a_live_grant_can_be_revoked(self):
        for state in (RequestStatus.PENDING, RequestStatus.DECLINED, RequestStatus.REVOKED, RequestStatus.CANCELLED):
            with self.subTest(state=state):
                request = self.pending(status=state)
                response = self.act(self.rdco, request, "revoke", note="No.")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        expired = self.granted(days=-1)
        self.assertEqual(self.act(self.rdco, expired, "revoke", note="No.").status_code, status.HTTP_400_BAD_REQUEST)
        expired.refresh_from_db()
        self.assertEqual(expired.status, RequestStatus.APPROVED)
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.DOWNLOAD_GRANT_REVOKED).exists())

    def test_only_rdco_revokes(self):
        grant = self.granted()
        for user in (self.reader, self.stranger, self.itso):
            with self.subTest(user=user.email):
                self.assertEqual(self.act(user, grant, "revoke", note="No.").status_code, status.HTTP_403_FORBIDDEN)
        grant.refresh_from_db()
        self.assertEqual(grant.status, RequestStatus.APPROVED)

    def test_the_queue_says_which_grants_rdco_may_revoke(self):
        live, expired = self.granted(), self.granted(days=-1)
        self.client.force_authenticate(self.rdco)
        rows = {row["id"]: row["grant_live"] for row in self.client.get(DOWNLOAD_REQUESTS).data["results"]}
        self.assertEqual((rows[live.pk], rows[expired.pk]), (True, False))
