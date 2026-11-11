"""
Verify an email address, and ask for the email again (IR-643, ADR-045).

The seams are the ones ADR-045 §9 names and IR-642's suite already uses: the
anonymous HTTP API with Django's real mail outbox, and the worker boundary --
`deliver_recovery_intent`, run here exactly as a `celery-default` process
would run it after the request commits. The suite's broker executes nothing,
which is also what proves the request path sends no mail of its own. The
race runs on real Postgres connections.

Only `apps.accounts.recovery.clock.now` is moved.
"""

import re
import threading
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import RecoveryIntent, RecoveryToken, Role, RoleRequest, User
from apps.accounts.recovery import service
from apps.accounts.recovery.delivery import deliver_recovery_intent
from apps.accounts.test_password_policy import registration
from apps.accounts.test_password_recovery import GENERIC_202, INVALID_LINK, Clock
from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from core.enums import RequestStatus, RoleName

RESEND = "/api/v1/auth/verification/resend/"
CONFIRM = "/api/v1/auth/verification/confirm/"
RESET_REQUEST = "/api/v1/auth/password/reset/request/"
RESET_CONFIRM = "/api/v1/auth/password/reset/confirm/"
LOGIN = "/api/v1/auth/login/"
PASSWORD = "Kalamansi-Tide-42"
ADDRESS = "newcomer@cit.edu"
VERIFIED = {"code": "email_verified", "detail": "Email verified. Return to sign-in."}
LINK = re.compile(r"/verify-email#token=([A-Za-z0-9_-]{43})\b")


class VerificationTestCase(APITestCase):
    def setUp(self):
        self.clock = Clock()
        patcher = patch("apps.accounts.recovery.clock.now", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rdco = Role.objects.get_or_create(name=RoleName.RDCO)[0]
        self.student = Role.objects.get_or_create(name=RoleName.STUDENT)[0]

    def unverified(self, email=ADDRESS, **flags):
        user = User.objects.create_user(email=email, password=PASSWORD, first_name="New",
                                        last_name="Comer", is_verified=False, **flags)
        RoleRequest.objects.create(user=user, requested_role=self.student)
        return user

    def resend(self, email=ADDRESS, ip="10.0.0.1"):
        return self.client.post(RESEND, {"email": email}, format="json", REMOTE_ADDR=ip)

    def confirm(self, token, ip="10.0.0.1", **extra):
        return self.client.post(CONFIRM, {"token": token}, format="json", REMOTE_ADDR=ip, **extra)

    def run_workers(self):
        for intent_id in RecoveryIntent.objects.values_list("id", flat=True):
            deliver_recovery_intent(str(intent_id))

    def token_from(self, message):
        match = LINK.search(message.body)
        self.assertIsNotNone(match, message.body)
        return match.group(1)

    def emailed_token(self, email=ADDRESS):
        self.assertEqual(self.resend(email).status_code, 202)
        self.run_workers()
        return self.token_from(mail.outbox[-1])

    def broadcasts(self):
        return Notification.objects.filter(broadcast_to_role=self.rdco)


# --- AC: resend, follow the link, verify, without registering again -----------------

class JourneyTests(VerificationTestCase):
    def test_registration_emails_a_link_that_verifies_once_it_is_posted(self):
        response = self.client.post(reverse("auth-register"),
                                    registration(PASSWORD), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(mail.outbox, [], "registration sends nothing itself; a worker does")
        self.assertEqual(self.client.post(LOGIN, {"email": ADDRESS, "password": PASSWORD},
                                          format="json").status_code, 403)

        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [ADDRESS])
        done = self.confirm(self.token_from(mail.outbox[0]))

        self.assertEqual((done.status_code, done.json()), (200, VERIFIED))
        self.assertTrue(User.objects.get(email=ADDRESS).is_verified)
        signed_in = self.client.post(LOGIN, {"email": ADDRESS, "password": PASSWORD}, format="json")
        self.assertNotEqual(signed_in.json().get("detail"), "Email not verified.")

    def test_an_unverified_person_asks_again_and_verifies_without_registering_again(self):
        user = self.unverified()
        response = self.resend()
        self.assertEqual((response.status_code, response.json()), (202, GENERIC_202))
        self.assertEqual(mail.outbox, [])

        self.run_workers()
        done = self.confirm(self.token_from(mail.outbox[0]))

        self.assertEqual(done.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        self.assertEqual(User.objects.filter(email=ADDRESS).count(), 1)

    def test_the_email_says_what_it_is_for_and_nothing_about_approval(self):
        self.unverified()
        with override_settings(FRONTEND_URL="https://iris.example.edu"):
            self.resend()
            self.run_workers()
        message = mail.outbox[0]
        token = RecoveryToken.objects.get()

        self.assertEqual(message.subject, "Verify your IRIS email address")
        self.assertIn("https://iris.example.edu/verify-email#token=", message.body)
        self.assertIn(f"expires at {token.expires_at.isoformat()} UTC", message.body)
        # ADR-051 decision 26 (IR-705) replaced "If you did not request this,
        # ignore this email." with who registered and when the account goes.
        self.assertIn("New Comer registered for an IRIS account", message.body)
        self.assertIn("If this wasn't you, ignore it. The account is deleted in 30 days.", message.body)
        self.assertIn("contact RDCO or your department administrator", message.body)
        for word in ("approve", "Student", "role", "password"):
            self.assertNotIn(word, message.body)
        self.assertEqual(token.expires_at - token.issued_at, timedelta(seconds=86400))

    def test_opening_or_prefetching_the_link_changes_nothing(self):
        user = self.unverified()
        self.emailed_token()

        self.assertEqual(self.client.get(CONFIRM).status_code, 405)
        self.assertEqual(self.client.head(CONFIRM).status_code, 405)
        user.refresh_from_db()
        self.assertFalse(user.is_verified)
        self.assertIsNone(RecoveryToken.objects.get().consumed_at)

    def test_the_answers_are_never_cached_and_send_no_referrer(self):
        self.unverified()
        for response in (self.resend(), self.confirm(self.emailed_token()), self.confirm("x" * 43)):
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response["Referrer-Policy"], "no-referrer")


# --- AC: verification is not approval -------------------------------------------------

class VerificationIsNotApprovalTests(VerificationTestCase):
    def test_it_changes_is_verified_alone_and_signs_no_one_in(self):
        user = self.unverified()
        before = User.objects.filter(pk=user.pk).values(
            "role_id", "is_active", "is_locked", "is_staff", "is_superuser", "email",
            "password", "credential_version", "ai_consent",
        ).get()

        done = self.confirm(self.emailed_token())

        self.assertNotIn("access", done.json())
        self.assertNotIn("refresh", done.json())
        after = User.objects.filter(pk=user.pk).values(*before).get()
        self.assertEqual(after, before)
        self.assertTrue(User.objects.get(pk=user.pk).is_verified)
        self.assertEqual(RoleRequest.objects.get(user=user).status, RequestStatus.PENDING)

    def test_rdco_hears_of_the_pending_request_once_on_the_first_verification(self):
        self.unverified()
        self.assertEqual(self.broadcasts().count(), 0)

        self.confirm(self.emailed_token())

        sent = self.broadcasts().get()
        self.assertEqual(sent.notif_type.name, "Role Request - Student")
        self.assertIn("New Comer requested the Student role.", sent.message)

    def test_a_decided_request_is_not_announced(self):
        user = self.unverified()
        RoleRequest.objects.filter(user=user).update(status=RequestStatus.APPROVED)
        self.confirm(self.emailed_token())
        self.assertEqual(self.broadcasts().count(), 0)

    def test_a_refused_link_alerts_nobody(self):
        self.unverified()
        self.confirm("x" * 43)
        self.assertEqual(self.broadcasts().count(), 0)


# --- AC: one answer for unknown, verified, locked and inactive accounts ---------------

class EligibilityTests(VerificationTestCase):
    """ADR-045 §1, at issuance: the answer is identical; only the mail differs."""

    def outcome(self, email):
        response = self.resend(email)
        self.run_workers()
        sent = [m for m in mail.outbox if m.to == [email]]
        return response, sent

    def test_every_address_gets_the_same_answer_and_only_the_eligible_one_mail(self):
        self.unverified("unverified@cit.edu")
        verified = self.unverified("verified@cit.edu")
        User.objects.filter(pk=verified.pk).update(is_verified=True)
        self.unverified("locked@cit.edu", is_locked=True)
        self.unverified("inactive@cit.edu", is_active=False)
        cases = {
            "unverified@cit.edu": 1, "verified@cit.edu": 0, "locked@cit.edu": 0,
            "inactive@cit.edu": 0, "nobody@cit.edu": 0,
        }
        bodies = set()
        for email, expected in cases.items():
            with self.subTest(email=email):
                response, sent = self.outcome(email)
                self.assertEqual(response.status_code, 202)
                bodies.add((response.content, response["Cache-Control"]))
                self.assertEqual(len(sent), expected)
        self.assertEqual(len(bodies), 1)
        self.assertFalse(User.objects.filter(email="nobody@cit.edu").exists())

    def test_the_request_path_does_not_look_the_address_up(self):
        self.unverified()
        with patch.object(User.objects, "filter", side_effect=AssertionError("looked up")), \
                patch.object(User.objects, "get", side_effect=AssertionError("looked up")):
            self.assertEqual(self.resend().status_code, 202)

    def test_an_address_typed_with_a_capital_domain_reaches_the_account(self):
        self.unverified()
        self.resend("newcomer@CIT.EDU")
        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)

    def test_a_badly_formed_request_is_a_field_error(self):
        for body, field in (({}, "email"), ({"email": "not-an-address"}, "email"),
                            ({"email": 5}, "email"), ({"email": ADDRESS, "extra": 1}, "extra")):
            with self.subTest(body=body):
                response = self.client.post(RESEND, body, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "validation_error")
                self.assertIn(field, response.json()["errors"])
        self.assertEqual(RecoveryIntent.objects.count(), 0)


# --- AC: expiry, purpose, replay, older links ----------------------------------------

class LinkTests(VerificationTestCase):
    """ADR-045 §1 and §3, at consumption."""

    def refused(self, token):
        response = self.confirm(token)
        self.assertEqual((response.status_code, response.json()), (400, INVALID_LINK))

    def test_a_link_works_once(self):
        self.unverified()
        token = self.emailed_token()
        self.assertEqual(self.confirm(token).status_code, 200)
        self.refused(token)

    def test_it_expires_exactly_24_hours_after_issuance(self):
        user = self.unverified()
        token = self.emailed_token()
        self.clock.advance(seconds=86400)
        self.refused(token)
        self.clock.advance(seconds=-1)
        self.assertEqual(self.confirm(token).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)

    def test_a_newer_email_retires_the_older_link(self):
        self.unverified()
        older = self.emailed_token()
        self.clock.advance(seconds=61)
        newer = self.emailed_token()
        self.assertNotEqual(older, newer)
        self.refused(older)
        self.assertEqual(self.confirm(newer).status_code, 200)

    def test_malformed_and_unknown_links_are_the_same_refusal(self):
        self.unverified()
        self.emailed_token()
        for token in ("", "short", "x" * 43, "!" * 43, "x" * 44):
            with self.subTest(token=token):
                self.refused(token)

    def test_a_verification_link_cannot_reset_a_password(self):
        user = self.unverified()
        token = self.emailed_token()
        response = self.client.post(RESET_CONFIRM, {
            "token": token, "new_password": "Different-pass-9", "confirm_password": "Different-pass-9",
        }, format="json")
        self.assertEqual((response.status_code, response.json()), (400, INVALID_LINK))
        self.assertTrue(User.objects.get(pk=user.pk).check_password(PASSWORD))
        self.assertEqual(self.confirm(token).status_code, 200, "the refusal did not use it up")

    def test_a_reset_link_cannot_verify_an_address(self):
        user = self.unverified()
        self.client.post(RESET_REQUEST, {"email": ADDRESS}, format="json")
        self.run_workers()
        reset = re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body).group(1)
        self.refused(reset)
        user.refresh_from_db()
        self.assertFalse(user.is_verified, "a reset never verifies (ADR-045 §1)")

    def test_locking_or_deactivating_after_the_email_refuses_the_link(self):
        for flag in ({"is_locked": True}, {"is_active": False}):
            with self.subTest(flag=flag):
                self.clock.advance(seconds=61)  # past the previous pass's cooldown
                RecoveryToken.objects.all().delete()
                User.objects.all().delete()
                mail.outbox.clear()
                user = self.unverified()
                token = self.emailed_token()
                User.objects.filter(pk=user.pk).update(**flag)
                self.refused(token)
                user.refresh_from_db()
                self.assertFalse(user.is_verified)
                self.assertEqual(user.is_locked, flag.get("is_locked", False))
                self.assertEqual(user.is_active, flag.get("is_active", True))

    def test_an_account_verified_some_other_way_refuses_its_old_link(self):
        user = self.unverified()
        token = self.emailed_token()
        User.objects.filter(pk=user.pk).update(is_verified=True)
        self.refused(token)

    def test_changing_the_address_retires_the_link(self):
        user = self.unverified()
        token = self.emailed_token()
        user.email = "moved@cit.edu"
        user.save()
        self.refused(token)

    def test_a_password_change_leaves_the_verification_link_working(self):
        user = self.unverified()
        token = self.emailed_token()
        user.set_password("Another-pass-77")
        user.save()
        self.assertEqual(self.confirm(token).status_code, 200)


# --- AC: cooldown and limits, with retry guidance -------------------------------------

class LimitTests(VerificationTestCase):
    def test_a_second_request_within_60_seconds_sends_no_second_email(self):
        self.unverified()
        first, second = self.resend(), self.resend()
        self.assertEqual(first.json(), second.json())
        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)

    def test_registration_starts_the_same_cooldown(self):
        self.client.post(reverse("auth-register"),
                         registration(PASSWORD), format="json")
        self.assertEqual(self.resend().status_code, 202)
        self.run_workers()
        self.assertEqual(len(mail.outbox), 1, "registration's email, and no second one")

        self.clock.advance(seconds=60)
        self.resend()
        self.run_workers()
        self.assertEqual(len(mail.outbox), 2)

    def test_a_reset_request_and_a_resend_share_the_address_cooldown(self):
        self.unverified()
        self.client.post(RESET_REQUEST, {"email": ADDRESS}, format="json")
        self.resend()
        self.run_workers()
        self.assertEqual([m.subject for m in mail.outbox], ["Reset your IRIS password"])

    def test_an_address_gets_at_most_five_emails_an_hour(self):
        self.unverified()
        for _ in range(7):
            self.assertEqual(self.resend().status_code, 202)
            self.run_workers()
            self.clock.advance(seconds=61)
        self.assertEqual(len(mail.outbox), 5)

    def test_ten_resends_from_one_address_in_ten_minutes_then_a_429_with_retry_after(self):
        for _ in range(10):
            self.assertEqual(self.resend(f"n{_}@cit.edu").status_code, 202)
        throttled = self.resend("n10@cit.edu")
        self.assertEqual(throttled.status_code, 429)
        self.assertEqual(throttled.json()["code"], "rate_limited")
        self.assertEqual(throttled["Retry-After"], str(throttled.json()["retry_after"]))
        self.assertEqual(self.resend("n11@cit.edu", ip="10.0.0.2").status_code, 202)

    def test_resend_and_reset_requests_are_counted_separately_by_ip(self):
        for _ in range(10):
            self.resend(f"n{_}@cit.edu")
        response = self.client.post(RESET_REQUEST, {"email": "other@cit.edu"}, format="json",
                                    REMOTE_ADDR="10.0.0.1")
        self.assertEqual(response.status_code, 202)

    def test_thirty_confirmations_in_ten_minutes_then_429(self):
        for _ in range(30):
            self.assertEqual(self.confirm("x" * 43).status_code, 400)
        self.assertEqual(self.confirm("x" * 43).status_code, 429)


# --- AC: atomic change, mail only after commit ----------------------------------------

class AtomicityTests(VerificationTestCase):
    def test_a_registration_that_rolls_back_leaves_no_intent_and_sends_nothing(self):
        real = service.admit_request

        def admit_then_fail(*args):
            real(*args)
            raise RuntimeError("registration failed after admission")

        with patch("apps.accounts.views.recovery_service.admit_request", admit_then_fail), \
                self.assertRaises(RuntimeError):
            self.client.post(reverse("auth-register"),
                             registration(PASSWORD), format="json")
        self.assertFalse(User.objects.filter(email=ADDRESS).exists())
        self.assertEqual(RecoveryIntent.objects.count(), 0)
        self.run_workers()
        self.assertEqual(mail.outbox, [])

    def test_the_intent_is_enqueued_only_after_commit(self):
        self.unverified()
        with patch("apps.accounts.recovery.service.enqueue") as enqueue:
            # TestCase wraps each test in a transaction, so on_commit runs only
            # at the outermost commit, which `captureOnCommitCallbacks` stands in for.
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                service.admit_request("email_verification", ADDRESS)
                enqueue.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            enqueue.assert_called_once()

    def test_a_failed_send_is_retried_with_the_same_link(self):
        self.unverified()
        self.resend()
        with patch("apps.accounts.recovery.delivery._send", side_effect=OSError("network")):
            self.run_workers()
        self.assertEqual(mail.outbox, [])
        self.clock.advance(seconds=30)
        self.run_workers()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(RecoveryToken.objects.count(), 1, "a retry issues no second token")


# --- AC: audit, and what never reaches it ---------------------------------------------

class AuditTests(VerificationTestCase):
    def test_completion_is_audited_against_the_account_with_allowlisted_metadata(self):
        user = self.unverified()
        token = self.emailed_token()
        self.confirm(token)

        event = AuditEvent.objects.get(event_type=AuditEvent.EMAIL_VERIFICATION_COMPLETED)
        self.assertEqual(event.user, user)
        self.assertEqual(set(event.metadata), {"purpose", "outcome", "correlation_id"})
        self.assertEqual(event.metadata["purpose"], "email_verification")

    def test_no_audit_row_carries_an_address_or_a_token(self):
        self.unverified()
        token = self.emailed_token()
        self.confirm(token)
        self.confirm(token)
        events = list(AuditEvent.objects.values_list("event_type", "metadata"))
        self.assertIn(AuditEvent.RECOVERY_TOKEN_REJECTED, [e for e, _ in events])
        for _, metadata in events:
            self.assertNotIn(ADDRESS, str(metadata))
            self.assertNotIn(token, str(metadata))


# --- AC: concurrent consumption -------------------------------------------------------

class ConcurrentVerificationTests(TransactionTestCase):
    """Two posts of one link on separate Postgres connections: one verifies."""

    def setUp(self):
        from apps.notifications.models import NotificationType

        # A TransactionTestCase empties every table, the migrations' seeded rows too.
        NotificationType.objects.get_or_create(name="Role Request - Student")
        self.rdco = Role.objects.get_or_create(name=RoleName.RDCO)[0]
        student = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        self.user = User.objects.create_user(email=ADDRESS, password=PASSWORD, first_name="R",
                                             last_name="C", is_verified=False)
        RoleRequest.objects.create(user=self.user, requested_role=student)

    def token(self):
        with patch("apps.accounts.recovery.service.enqueue"):
            service.admit_request("email_verification", ADDRESS)
        deliver_recovery_intent(str(RecoveryIntent.objects.get().pk))
        return LINK.search(mail.outbox[-1].body).group(1)

    def race(self, *calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)

        def run(index, call):
            try:
                barrier.wait(10)
                results[index] = call()
            except Exception as exc:  # noqa: BLE001 -- reported below
                results[index] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        return results

    def test_two_posts_of_one_link_have_exactly_one_winner_and_one_notice(self):
        token = self.token()

        def consume():
            service.confirm_verification(token)
            return "verified"

        results = self.race(consume, consume)
        self.assertEqual(results.count("verified"), 1, results)
        self.assertEqual(sum(isinstance(r, service.InvalidLink) for r in results), 1, results)
        self.assertTrue(User.objects.get(pk=self.user.pk).is_verified)
        self.assertEqual(Notification.objects.filter(broadcast_to_role=self.rdco).count(), 1)

    def test_issuing_a_new_link_racing_the_old_one_s_use_leaves_one_consistent_outcome(self):
        """ADR-045 §3: whichever commits first decides. Issuance happens in the
        worker, so that is what races the confirmation."""
        from apps.accounts.models import RecoveryAttempt

        token = self.token()
        RecoveryAttempt.objects.all().delete()  # past the cooldown, without moving a shared clock
        with patch("apps.accounts.recovery.service.enqueue"):
            service.admit_request("email_verification", ADDRESS)
        newer = RecoveryIntent.objects.get(status=RecoveryIntent.Status.PENDING)

        def issue():
            deliver_recovery_intent(str(newer.pk))
            return "issued"

        def consume():
            try:
                service.confirm_verification(token)
                return "verified"
            except service.InvalidLink:
                return "refused"

        results = self.race(issue, consume)
        verified = User.objects.get(pk=self.user.pk).is_verified
        usable = RecoveryToken.objects.filter(consumed_at__isnull=True, revoked_at__isnull=True).count()
        if results[1] == "verified":
            self.assertTrue(verified)
            self.assertEqual(usable, 0, "a verified account is issued no new link")
        else:
            self.assertEqual(results[1], "refused", results)
            self.assertFalse(verified)
            self.assertEqual(usable, 1, "the new link replaced the old one")
