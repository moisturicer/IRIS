"""
Unverified registrations (ADR-051 decisions 22 to 26, IR-705).

An account whose registrant has not verified their email is an *unverified
registration*. RDCO never sees it, nobody can make it a co-owner, it expires a
set number of days after registering, and registering again on its address
replaces it. Expiring and replacing are not Account deletion.

The seams: the HTTP API for registration, RDCO's views and co-owners; the
expiry run called directly with the time it should believe it is; and the
verification email as the worker composes it.
"""

import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import DataNotice, RecoveryIntent, Role, RoleRequest, User
from apps.accounts.recovery.delivery import deliver_recovery_intent
from apps.accounts.test_password_recovery import Clock
from apps.accounts.test_system_admin import make
from apps.accounts.unverified import expire_unverified_registrations
from apps.audit.models import AuditEvent
from apps.records.models import Record, RecordOwner, RecordType
from apps.reviews.models import RecordAssignment, ReviewerSeat
from core.enums import PipelineStatus, RequestStatus, RoleName

ADDRESS = "newcomer@cit.edu"
PASSWORD = "Kalamansi-Tide-42"
CONFIRM = "/api/v1/auth/verification/confirm/"
LINK = re.compile(r"/verify-email#token=([A-Za-z0-9_-]{43})\b")
ALREADY = ["This email address is already registered."]


class Base(APITestCase):
    def setUp(self):
        self.clock = Clock()
        patcher = patch("apps.accounts.recovery.clock.now", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.student_role = Role.objects.get(name=RoleName.STUDENT)
        self.thesis = RecordType.objects.get_or_create(name="Thesis / Research")[0]

    def register(self, email=ADDRESS, first="New", middle="", last="Comer"):
        self.client.force_authenticate(None)
        course = self.course()
        return self.client.post(reverse("auth-register"), {
            "email": email, "first_name": first, "middle_initial": middle, "last_name": last,
            "password": PASSWORD, "confirm_password": PASSWORD,
            "notice_version": DataNotice.current().number, "agree_dpa": True, "ai_consent": True,
            "role_name": RoleName.STUDENT, "course_id": course.pk,
        }, format="json")

    def course(self):
        from apps.accounts.models import College, Course, Department
        college = College.objects.get_or_create(code="T705", defaults={"name": "College"})[0]
        department = Department.objects.get_or_create(code="T705", defaults={"name": "Dept", "college": college})[0]
        return Course.objects.get_or_create(name="BS Computer Science", department=department)[0]

    def unverified(self, email=ADDRESS, joined_days_ago=0):
        user = User.objects.create_user(email=email, password=PASSWORD, first_name="Old",
                                        last_name="Name", is_verified=False)
        RoleRequest.objects.create(user=user, requested_role=self.student_role)
        if joined_days_ago:
            User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=joined_days_ago))
        return user

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def run_workers(self):
        for intent_id in RecoveryIntent.objects.values_list("id", flat=True):
            deliver_recovery_intent(str(intent_id))

    def paper(self, owners, *, adviser=None, status=PipelineStatus.DRAFT):
        record = Record.objects.create(title="A paper", record_type=self.thesis, added_by=owners[0],
                                       pipeline_status=status, adviser=adviser)
        for owner in owners:
            RecordOwner.objects.create(record=record, user=owner, is_primary=owner == owners[0])
        return record


# --- Registering again replaces an unverified registration --------------------------

class RegisteringAgainTests(Base):
    def test_a_verified_address_still_says_already_registered(self):
        make(ADDRESS, RoleName.STUDENT)
        response = self.register()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["email"], ALREADY)

    def test_an_unverified_address_is_replaced_and_its_earlier_link_stops_working(self):
        earlier = self.unverified()
        self.as_(None).post("/api/v1/auth/verification/resend/", {"email": ADDRESS}, format="json")
        self.run_workers()
        old_token = LINK.search(mail.outbox[-1].body).group(1)
        self.clock.advance(seconds=3600)  # past the address's cooldown and hourly limit

        response = self.register(first="Real", last="Person")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(User.objects.filter(pk=earlier.pk).exists())
        self.assertFalse(RoleRequest.objects.filter(user_id=earlier.pk).exists())
        now = User.objects.get(email=ADDRESS)
        self.assertEqual((now.first_name, now.last_name, now.is_verified), ("Real", "Person", False))
        self.assertEqual(RoleRequest.objects.filter(user=now, status=RequestStatus.PENDING).count(), 1)

        refused = self.as_(None).post(CONFIRM, {"token": old_token}, format="json")
        self.assertEqual(refused.status_code, 400, refused.content)

        mail.outbox.clear()
        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [ADDRESS])
        self.assertIn("Real Person registered", mail.outbox[0].body)

    def test_replacing_writes_an_audit_event_naming_only_the_earlier_account(self):
        earlier = self.unverified()
        self.assertEqual(self.register().status_code, 201)
        event = AuditEvent.objects.get(event_type=AuditEvent.REGISTRATION_REPLACED)
        self.assertEqual(event.user_id, earlier.pk)
        self.assertEqual(event.metadata, {})

    def test_an_unverified_address_something_links_to_says_already_registered(self):
        owner = make("owner@cit.edu", RoleName.STUDENT)
        for link in ("co-owner", "adviser", "seat"):
            with self.subTest(link=link):
                User.objects.filter(email=ADDRESS).delete()
                linked = self.unverified()
                if link == "co-owner":
                    self.paper([owner, linked])
                elif link == "adviser":
                    self.paper([owner], adviser=linked)
                else:
                    ReviewerSeat.objects.create(
                        assignment=RecordAssignment.objects.create(record=self.paper([owner]), party="itso"),
                        reviewer=linked, source="claimed", state="withdrawn",
                    )
                response = self.register()
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()["email"], ALREADY)
                self.assertTrue(User.objects.filter(pk=linked.pk).exists())

    def test_too_soon_is_refused_with_retry_guidance_and_changes_nothing(self):
        earlier = self.unverified()
        self.assertEqual(self.as_(None).post("/api/v1/auth/verification/resend/", {"email": ADDRESS},
                                             format="json").status_code, 202)
        intents = RecoveryIntent.objects.count()

        response = self.register(first="Real", last="Person")

        self.assertEqual(response.status_code, 429, response.content)
        body = response.json()
        self.assertEqual(body["code"], "rate_limited")
        self.assertGreater(body["retry_after"], 0)
        self.assertEqual(response["Retry-After"], str(body["retry_after"]))
        self.assertTrue(User.objects.filter(pk=earlier.pk, first_name="Old").exists())
        self.assertEqual(RecoveryIntent.objects.count(), intents)
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.REGISTRATION_REPLACED).exists())


# --- RDCO sees verified accounts only -----------------------------------------------

class RdcoSeesVerifiedOnlyTests(Base):
    def setUp(self):
        super().setUp()
        self.rdco = make("rdco@cit.edu", RoleName.RDCO)
        self.sysadmin = make("sysadmin@cit.edu", RoleName.SYSTEM_ADMIN)
        self.pending = self.unverified()
        self.verified = make("verified@cit.edu")
        RoleRequest.objects.create(user=self.verified, requested_role=self.student_role)

    def emails(self, response):
        data = response.json()
        return {row["email"] for row in data.get("results", data)}

    def test_the_role_request_list_leaves_unverified_accounts_out(self):
        data = self.as_(self.rdco).get(reverse("role-request-list")).json()
        listed = {row["user"] for row in data.get("results", data)}
        self.assertIn(self.verified.pk, listed)
        self.assertNotIn(self.pending.pk, listed)

    def test_an_unverified_accounts_role_request_cannot_be_approved(self):
        request = RoleRequest.objects.get(user=self.pending)
        response = self.as_(self.rdco).patch(reverse("role-request-detail", args=[request.pk]),
                                             {"action": "approve"}, format="json")
        self.assertEqual(response.status_code, 404, response.content)
        request.refresh_from_db()
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.pending.refresh_from_db()
        self.assertIsNone(self.pending.role)

    def test_rdcos_users_page_and_user_detail_leave_unverified_accounts_out(self):
        self.assertNotIn(ADDRESS, self.emails(self.as_(self.rdco).get(reverse("user-list"))))
        self.assertIn("verified@cit.edu", self.emails(self.as_(self.rdco).get(reverse("user-list"))))
        detail = self.as_(self.rdco).get(reverse("user-detail", args=[self.pending.pk]))
        self.assertEqual(detail.status_code, 404, detail.content)

    def test_the_system_admin_still_sees_them(self):
        self.assertIn(ADDRESS, self.emails(self.as_(self.sysadmin).get(reverse("user-list"))))
        detail = self.as_(self.sysadmin).get(reverse("user-detail", args=[self.pending.pk]))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertFalse(detail.json()["is_verified"])


# --- Co-owners must be verified -----------------------------------------------------

class CoOwnersMustBeVerifiedTests(Base):
    def test_owner_emails_refuses_an_unverified_account(self):
        owner = make("owner@cit.edu", RoleName.STUDENT)
        pending = self.unverified()
        record = self.paper([owner])
        url = reverse("record-detail", args=[record.pk])

        refused = self.as_(owner).patch(url, {"owner_emails": [owner.email, pending.email]}, format="json")
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(refused.json()["owner_emails"],
                         ["Use existing verified accounts, include yourself, and exclude the Adviser."])
        self.assertFalse(record.owners.filter(user=pending).exists())

        pending.is_verified = True
        pending.save(update_fields=["is_verified"])
        accepted = self.as_(owner).patch(url, {"owner_emails": [owner.email, pending.email]}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.content)


# --- Unverified registrations expire ------------------------------------------------

@override_settings(UNVERIFIED_REGISTRATION_DAYS=30)
class ExpiryTests(Base):
    def test_the_thirty_day_boundary(self):
        now = timezone.now()
        kept = self.unverified("kept@cit.edu")
        gone = self.unverified("gone@cit.edu")
        User.objects.filter(pk=kept.pk).update(date_joined=now - timedelta(days=30) + timedelta(seconds=1))
        User.objects.filter(pk=gone.pk).update(date_joined=now - timedelta(days=30))
        verified = make("old-verified@cit.edu")
        User.objects.filter(pk=verified.pk).update(date_joined=now - timedelta(days=400))

        self.assertEqual(expire_unverified_registrations(now=now), {"expired": 1, "skipped": 0})

        self.assertTrue(User.objects.filter(pk=kept.pk).exists())
        self.assertFalse(User.objects.filter(pk=gone.pk).exists())
        self.assertFalse(RoleRequest.objects.filter(user_id=gone.pk).exists())
        self.assertTrue(User.objects.filter(pk=verified.pk).exists())

    def test_a_linked_account_is_skipped_and_logged_by_id_only(self):
        owner = make("owner@cit.edu", RoleName.STUDENT)
        linked = self.unverified(joined_days_ago=45)
        self.paper([owner], adviser=linked)
        with self.assertLogs("apps.accounts.unverified", level="WARNING") as logs:
            self.assertEqual(expire_unverified_registrations(), {"expired": 0, "skipped": 1})
        self.assertTrue(User.objects.filter(pk=linked.pk).exists())
        self.assertIn(str(linked.pk), logs.output[0])
        self.assertNotIn(ADDRESS, logs.output[0])

    def test_a_run_writes_one_audit_event_with_counts_and_a_repeat_changes_nothing(self):
        self.unverified("a@cit.edu", joined_days_ago=31)
        self.unverified("b@cit.edu", joined_days_ago=60)
        self.assertEqual(expire_unverified_registrations(), {"expired": 2, "skipped": 0})
        self.assertEqual(expire_unverified_registrations(), {"expired": 0, "skipped": 0})

        runs = AuditEvent.objects.filter(event_type=AuditEvent.UNVERIFIED_REGISTRATIONS_EXPIRED).order_by("pk")
        self.assertEqual([(e.user_id, e.metadata) for e in runs],
                         [(None, {"expired": 2, "skipped": 0}), (None, {"expired": 0, "skipped": 0})])

    def test_audit_rows_of_an_expired_account_stay(self):
        gone = self.unverified(joined_days_ago=31)
        AuditEvent.objects.create(event_type=AuditEvent.FAILED_LOGIN, user=gone)
        expire_unverified_registrations()
        self.assertFalse(User.objects.filter(pk=gone.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.FAILED_LOGIN, user_id=gone.pk).exists())

    @override_settings(UNVERIFIED_REGISTRATION_DAYS=7)
    def test_the_period_is_the_setting(self):
        gone = self.unverified(joined_days_ago=8)
        expire_unverified_registrations()
        self.assertFalse(User.objects.filter(pk=gone.pk).exists())

    def test_beat_runs_it_daily_at_three_in_the_morning_manila(self):
        from django.conf import settings
        entry = settings.CELERY_BEAT_SCHEDULE["unverified-registrations"]
        self.assertEqual(entry["task"], "apps.accounts.tasks.expire_unverified_registrations")
        self.assertEqual((entry["schedule"].hour, entry["schedule"].minute), ({19}, {0}))


# --- The email says who registered --------------------------------------------------

@override_settings(UNVERIFIED_REGISTRATION_DAYS=30)
class VerificationEmailTests(Base):
    def test_it_names_the_registrant_and_when_the_account_is_deleted(self):
        self.assertEqual(self.register(first="Ashlee", middle="S.", last="Abac").status_code, 201)
        self.run_workers()
        body = mail.outbox[-1].body
        self.assertIn("Ashlee S. Abac registered for an IRIS account with this email address.", body)
        self.assertIn("If this wasn't you, ignore it. The account is deleted in 30 days.", body)

    def test_a_resent_link_says_the_same(self):
        self.unverified()
        self.as_(None).post("/api/v1/auth/verification/resend/", {"email": ADDRESS}, format="json")
        self.run_workers()
        body = mail.outbox[-1].body
        self.assertIn("Old Name registered for an IRIS account with this email address.", body)
        self.assertIn("If this wasn't you, ignore it. The account is deleted in 30 days.", body)
