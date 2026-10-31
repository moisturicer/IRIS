"""
IR-675: an approved request is a time-limited grant, used while signed in.

`GET /records/<id>/download/` serves the manuscript to an exempt reader or the
holder of a live grant, and tells everyone else who can see the record why not.
The bearer link it replaces could be forwarded and left no audit row (ADR-048).
The per-role matrix row is in `apps/tests/access/table.py`.

**Seam: the API**, plus the migration's function for requests made before this.
"""

from datetime import timedelta
from importlib import import_module
from unittest import mock

from django.apps import apps as django_apps
from django.conf import settings
from django.test import override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.documents.testing import pdf_upload
from apps.notifications.models import Notification
from apps.records.models import DownloadRequest, Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment, ReviewerSeat
from core.enums import Party, PipelineStatus, RecordTypeName, RequestStatus, RoleName

DOWNLOAD_REQUESTS = "/api/v1/records/download-requests/"


def _user(email, role_name=RoleName.STUDENT):
    return User.objects.create_user(
        email=email, password="TestPass123!", first_name="Test", last_name="User",
        role=Role.objects.get_or_create(name=role_name)[0], is_verified=True,
    )


class Fixtures(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.reader = _user("grant-reader@cit.edu")
        cls.owner = _user("grant-owner@cit.edu")
        cls.adviser = _user("grant-adviser@cit.edu", RoleName.ADVISER)
        cls.rdco = _user("grant-rdco@cit.edu", RoleName.RDCO)
        cls.record = cls._record("A published thesis", PipelineStatus.PUBLISHED)
        cls.url = f"/api/v1/records/{cls.record.pk}/download/"

    @classmethod
    def _record(cls, title, pipeline_status):
        record = Record.objects.create(
            title=title, pipeline_status=pipeline_status, adviser=cls.adviser,
            record_type=RecordType.objects.get_or_create(name=RecordTypeName.THESIS_RESEARCH)[0],
            abstract_file=pdf_upload("thesis.pdf"),
        )
        RecordOwner.objects.create(record=record, user=cls.owner, is_primary=True)
        return record

    def request_by(self, user=None, state=RequestStatus.APPROVED, expires_in=30):
        return DownloadRequest.objects.create(
            record=self.record, requested_by=user or self.reader, status=state,
            grant_expires_at=(
                timezone.now() + timedelta(days=expires_in) if expires_in is not None else None
            ),
        )

    def get(self, user=None):
        self.client.force_authenticate(user or self.reader)
        return self.client.get(self.url)

    def assert_refused(self, code, user=None):
        response = self.get(user)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.content)
        self.assertEqual(response.data["code"], code)
        self.assertFalse(AuditEvent.objects.filter(record=self.record, event_type="DOWNLOAD").exists())

    def assert_served(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK, getattr(response, "data", ""))
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))


class ExemptReadersTests(Fixtures):

    def _seated_reviewer(self):
        itso = _user("grant-seated@cit.edu", RoleName.ADVISER)
        assignment = RecordAssignment.objects.create(record=self.record, party=Party.ITSO)
        ReviewerSeat.objects.create(assignment=assignment, reviewer=itso)
        return itso

    def test_each_exempt_reader_downloads_with_no_request(self):
        readers = {
            "record_owner": self.owner,
            "record_adviser": self.adviser,
            "assigned_reviewer": self._seated_reviewer(),
        }
        for role in (RoleName.ITSO, RoleName.IERC, RoleName.KTTO, RoleName.RDCO):
            readers[f"office_staff:{role}"] = _user(f"grant-office-{role.lower()}@cit.edu", role)

        for name, user in readers.items():
            with self.subTest(reader=name):
                self.assert_served(self.get(user))
                event = AuditEvent.objects.filter(
                    record=self.record, event_type="DOWNLOAD", user=user,
                ).get()
                self.assertEqual(event.metadata["source"], "exempt")
                self.assertEqual(event.metadata["exemption"], name.split(":")[0])
                self.assertNotIn("request", event.metadata)


class GrantTests(Fixtures):

    def test_a_live_grant_downloads_and_can_download_again(self):
        grant = self.request_by()

        self.assert_served(self.get())
        self.assert_served(self.get())

        events = AuditEvent.objects.filter(record=self.record, event_type="DOWNLOAD", user=self.reader)
        self.assertEqual(events.count(), 2)
        self.assertEqual(events.first().metadata, {"source": "grant", "request": grant.pk})

    def test_no_request_is_refused(self):
        self.assert_refused("request_needed")

    def test_a_pending_request_is_refused(self):
        self.request_by(state=RequestStatus.PENDING, expires_in=None)
        self.assert_refused("request_pending")

    def test_a_declined_request_is_refused(self):
        self.request_by(state=RequestStatus.DECLINED, expires_in=None)
        self.assert_refused("request_declined")

    def test_a_revoked_grant_is_refused_even_before_it_expires(self):
        self.request_by(state=RequestStatus.REVOKED)
        self.assert_refused("request_revoked")

    def test_an_expired_grant_is_refused(self):
        self.request_by(expires_in=-1)
        self.assert_refused("grant_expired")

    def test_an_approval_with_no_expiry_is_refused_not_unlimited(self):
        self.request_by(expires_in=None)
        self.assert_refused("grant_expired")

    def test_another_readers_grant_gives_nothing(self):
        self.request_by(user=_user("grant-holder@cit.edu"))
        self.assert_refused("request_needed")

    def test_a_grant_on_another_record_gives_nothing(self):
        other = self._record("Another thesis", PipelineStatus.PUBLISHED)
        DownloadRequest.objects.create(
            record=other, requested_by=self.reader, status=RequestStatus.APPROVED,
            grant_expires_at=timezone.now() + timedelta(days=30),
        )
        self.assert_refused("request_needed")

    def test_a_record_the_reader_cannot_see_reads_as_missing_even_with_a_grant(self):
        hidden = self._record("A draft", PipelineStatus.DRAFT)
        DownloadRequest.objects.create(
            record=hidden, requested_by=self.reader, status=RequestStatus.APPROVED,
            grant_expires_at=timezone.now() + timedelta(days=30),
        )
        self.client.force_authenticate(self.reader)

        response = self.client.get(f"/api/v1/records/{hidden.pk}/download/")
        missing = self.client.get("/api/v1/records/999999/download/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.content, missing.content)

    def test_signing_in_is_required(self):
        self.request_by()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_rule_is_the_same_whatever_the_declared_origin(self):
        for origin, _ in Record._meta.get_field("origin").choices:
            with self.subTest(origin=origin):
                Record.objects.filter(pk=self.record.pk).update(origin=origin)
                self.assertEqual(self.get().data["code"], "request_needed")


class WhichRequestCountsTests(Fixtures):

    def test_revoking_the_newest_is_not_undone_by_an_older_approval(self):
        self.request_by()
        self.request_by(state=RequestStatus.REVOKED)
        self.assert_refused("request_revoked")

    def test_a_pending_request_does_not_end_a_live_grant(self):
        self.request_by()
        self.request_by(state=RequestStatus.PENDING, expires_in=None)
        self.assert_served(self.get())

    def test_a_new_pending_request_replaces_a_declined_one(self):
        self.request_by(state=RequestStatus.DECLINED, expires_in=None)
        self.request_by(state=RequestStatus.PENDING, expires_in=None)
        self.assert_refused("request_pending")


class ApprovalRecordsAGrantTests(Fixtures):

    def approve(self, request):
        self.client.force_authenticate(self.rdco)
        return self.client.post(f"{DOWNLOAD_REQUESTS}{request.pk}/approve/", {}, format="json")

    @override_settings(DOWNLOAD_GRANT_DAYS=7)
    def test_approving_stores_an_expiry_from_the_setting_and_the_reader_can_download(self):
        request = self.request_by(state=RequestStatus.PENDING, expires_in=None)

        self.assertEqual(self.approve(request).status_code, status.HTTP_200_OK)

        request.refresh_from_db()
        self.assertEqual(request.grant_expires_at, request.reviewed_at + timedelta(days=7))
        self.assert_served(self.get())

    def test_declining_stores_no_expiry(self):
        request = self.request_by(state=RequestStatus.PENDING, expires_in=None)
        self.client.force_authenticate(self.rdco)

        self.client.post(f"{DOWNLOAD_REQUESTS}{request.pk}/decline/", {}, format="json")

        request.refresh_from_db()
        self.assertIsNone(request.grant_expires_at)

    def test_the_notice_says_when_and_links_to_the_record_never_a_file(self):
        request = self.request_by(state=RequestStatus.PENDING, expires_in=None)

        with mock.patch("apps.notifications.services.send_email_async") as send_email:
            self.approve(request)

        request.refresh_from_db()
        expires = timezone.localtime(request.grant_expires_at).strftime("%d %B %Y")
        self.assertIn(
            expires,
            Notification.objects.get(recipient=self.reader, notif_type__name="Download Request Approved").message,
        )
        body = send_email.call_args.kwargs["message"]
        self.assertIn(expires, body)
        self.assertIn(f"/records/{self.record.pk}", body)
        self.assertNotIn("token", body)
        self.assertNotIn("/download", body)

    def test_neither_decision_route_returns_a_link(self):
        request = self.request_by(state=RequestStatus.PENDING, expires_in=None)
        self.client.force_authenticate(self.rdco)

        response = self.client.patch(f"{DOWNLOAD_REQUESTS}{request.pk}/", {"action": "approve"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("download_url", response.data)
        self.assertIsNotNone(response.data["grant_expires_at"])


class TheBearerLinkIsGoneTests(Fixtures):

    def test_the_redeem_route_no_longer_exists(self):
        with self.assertRaises(NoReverseMatch):
            reverse("download-redeem")
        self.client.force_authenticate(None)
        response = self.client.get("/api/v1/records/download/", {"token": "anything"})
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND))
        self.assertFalse(response.has_header("Content-Disposition"))


class RequestingAgainTests(Fixtures):

    def post(self):
        self.client.force_authenticate(self.reader)
        return self.client.post(DOWNLOAD_REQUESTS, {"record": self.record.pk}, format="json")

    def test_an_ended_request_may_be_made_again(self):
        cases = {
            "expired": {"state": RequestStatus.APPROVED, "expires_in": -1},
            "declined": {"state": RequestStatus.DECLINED, "expires_in": None},
            "revoked": {"state": RequestStatus.REVOKED, "expires_in": 5},
        }
        for name, kwargs in cases.items():
            with self.subTest(previous=name):
                self.request_by(**kwargs)
                self.assertEqual(self.post().status_code, status.HTTP_201_CREATED)
                DownloadRequest.objects.all().delete()

    def test_a_second_pending_request_is_refused(self):
        self.request_by(state=RequestStatus.PENDING, expires_in=None)
        self.assertEqual(self.post().status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_live_grant_needs_no_new_request(self):
        self.request_by()
        self.assertEqual(self.post().status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(DownloadRequest.objects.count(), 1)

    def test_the_new_request_cannot_set_its_own_expiry(self):
        self.client.force_authenticate(self.reader)
        response = self.client.post(
            DOWNLOAD_REQUESTS,
            {"record": self.record.pk, "grant_expires_at": "2099-01-01T00:00:00Z"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(DownloadRequest.objects.get().grant_expires_at)


class RequestsMadeBeforeThisChangeTests(Fixtures):

    def test_only_approved_requests_get_a_grant_and_it_runs_from_the_migration(self):
        approved = self.request_by(expires_in=None)
        pending = self.request_by(user=self.adviser, state=RequestStatus.PENDING, expires_in=None)
        declined = self.request_by(user=self.rdco, state=RequestStatus.DECLINED, expires_in=None)
        before = timezone.now()

        import_module("apps.records.migrations.0022_download_grant").grant_existing_approvals(django_apps, None)

        for request in (approved, pending, declined):
            request.refresh_from_db()
        self.assertGreaterEqual(approved.grant_expires_at, before + timedelta(days=settings.DOWNLOAD_GRANT_DAYS))
        self.assertIsNone(pending.grant_expires_at)
        self.assertIsNone(declined.grant_expires_at)
        self.assert_served(self.get())
