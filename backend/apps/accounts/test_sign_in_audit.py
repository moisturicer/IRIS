"""
Every sign-in decision and every registration is audited (IR-659, ASVS 7.2.1).

Driven through the real endpoints, with each event read back from `AuditEvent`.
Decided 2026-11-15 (Hermoine Zozobrado):

* A refusal is `FAILED_LOGIN` with a `reason`: `invalid_credentials`,
  `unverified`, `locked_by_admin`, or `too_many_attempts` for every attempt axes
  refuses (one per 429, not one per lock). Each carries the email tried, and no
  client address (decided 2026-11-16: an audit row is never erased, so an
  address in one could never expire).
* A refusal names the account only when the password was right (unverified,
  locked by RDCO): a guess must not add rows to someone else's history.
* Registering writes `ACCOUNT_REGISTERED` against the new account.
* Activation was already audited (`EMAIL_VERIFICATION_COMPLETED`, IR-643);
  `test_email_verification.AuditTests` drives it.

No event may hold a password, token or link (ASVS 7.1.1).
"""
from django.conf import settings
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import RecoveryIntent, Role, User
from apps.accounts.recovery.delivery import deliver_recovery_intent
from apps.accounts.test_email_verification import LINK
from apps.accounts.test_password_policy import registration
from apps.audit.models import AuditEvent

PASSWORD = "Correct-horse-1!"
ADDRESS = "sign.in@cit.edu"
IP = "203.0.113.7"


def make_user(email=ADDRESS, **extra):
    extra.setdefault("is_verified", True)
    return User.objects.create_user(
        email=email, password=PASSWORD, first_name="Test", last_name="User",
        role=Role.objects.get_or_create(name="Student")[0], **extra,
    )


class SignInAuditCase(APITestCase):
    def sign_in(self, email=ADDRESS, password=PASSWORD, **headers):
        headers.setdefault("REMOTE_ADDR", IP)
        return self.client.post(
            reverse("auth-login"), {"email": email, "password": password}, format="json", **headers,
        )

    def refusals(self):
        return list(AuditEvent.objects.filter(event_type=AuditEvent.FAILED_LOGIN).order_by("pk"))

    def assertHoldsNoSecret(self, *secrets):
        for event in AuditEvent.objects.all():
            for secret in secrets:
                self.assertNotIn(secret, str(event.metadata), event.event_type)


class RefusalTests(SignInAuditCase):
    def test_a_wrong_password_records_the_reason_and_address_and_names_no_account(self):
        make_user()
        self.assertEqual(self.sign_in(password="Wrong-horse-1!").status_code, status.HTTP_401_UNAUTHORIZED)

        [event] = self.refusals()
        self.assertIsNone(event.user)
        self.assertEqual(event.metadata, {"email": ADDRESS, "reason": "invalid_credentials"})
        self.assertHoldsNoSecret("Wrong-horse-1!")

    def test_an_unknown_email_is_recorded_the_same_way(self):
        self.sign_in(email="nobody@cit.edu")

        [event] = self.refusals()
        self.assertIsNone(event.user)
        self.assertEqual(event.metadata["reason"], "invalid_credentials")

    def test_an_unverified_account_is_recorded_against_that_account(self):
        user = make_user(is_verified=False)
        self.assertEqual(self.sign_in().status_code, status.HTTP_403_FORBIDDEN)

        [event] = self.refusals()
        self.assertEqual(event.user, user)
        self.assertEqual(event.metadata, {"email": ADDRESS, "reason": "unverified"})
        self.assertHoldsNoSecret(PASSWORD)

    def test_an_account_locked_by_rdco_is_recorded_against_that_account(self):
        user = make_user(is_locked=True)
        self.assertEqual(self.sign_in().status_code, status.HTTP_403_FORBIDDEN)

        [event] = self.refusals()
        self.assertEqual(event.user, user)
        self.assertEqual(event.metadata, {"email": ADDRESS, "reason": "locked_by_admin"})

    def test_a_successful_sign_in_records_no_refusal(self):
        make_user()
        response = self.sign_in()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(self.refusals(), [])
        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.LOGIN).exists())
        self.assertHoldsNoSecret(PASSWORD, response.json()["access"], response.json()["refresh"])

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_no_refusal_stores_the_client_address(self):
        # Decided 2026-11-16: an audit row can never be erased, so an address in one
        # could never expire. Neither the peer nor the forwarded client is kept.
        make_user(is_verified=False)
        self.sign_in(password="x", REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR=IP)
        self.sign_in(REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR=IP)

        self.assertEqual(len(self.refusals()), 2)
        self.assertHoldsNoSecret(IP, "10.0.0.2")


# The lockout is off by default for now (IR-865); these prove it is audited when on.
@override_settings(AXES_ENABLED=True)
class LockoutTests(SignInAuditCase):
    def lock_out(self):
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.assertEqual(self.sign_in(password="wrong").status_code, status.HTTP_401_UNAUTHORIZED)
        return self.sign_in(password="wrong")

    def test_the_attempt_that_trips_the_lock_is_recorded_as_too_many_attempts(self):
        make_user()
        self.assertEqual(self.lock_out().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        reasons = [event.metadata["reason"] for event in self.refusals()]
        limit = settings.AXES_FAILURE_LIMIT
        self.assertEqual(reasons, ["invalid_credentials"] * (limit - 1) + ["too_many_attempts"])
        last = self.refusals()[-1]
        self.assertIsNone(last.user)
        self.assertEqual(last.metadata, {"email": ADDRESS, "reason": "too_many_attempts"})

    def test_every_attempt_refused_during_the_lock_is_recorded_even_with_the_right_password(self):
        make_user()
        self.lock_out()
        self.assertEqual(self.sign_in().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        last_two = [event.metadata["reason"] for event in self.refusals()[-2:]]
        self.assertEqual(last_two, ["too_many_attempts", "too_many_attempts"])
        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.LOGIN).exists())
        self.assertHoldsNoSecret(PASSWORD, "wrong")


@override_settings(AXES_ENABLED=True)
class AsgiLockoutTests(APITestCase):
    """Production serves ASGI, where axes calls the lockout callable with other arguments (IR-555)."""

    async def test_the_lockout_is_recorded_with_the_email_tried_under_asgi_too(self):
        from asgiref.sync import sync_to_async

        await sync_to_async(make_user)()
        body = {"email": ADDRESS, "password": "wrong"}
        for _ in range(settings.AXES_FAILURE_LIMIT):
            response = await self.async_client.post(reverse("auth-login"), body, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        last = await AuditEvent.objects.filter(event_type=AuditEvent.FAILED_LOGIN).alatest("pk")
        self.assertEqual(last.metadata["reason"], "too_many_attempts")
        self.assertEqual(last.metadata["email"], ADDRESS)
        self.assertNotIn("ip", last.metadata)
        self.assertEqual(
            await AuditEvent.objects.filter(event_type=AuditEvent.FAILED_LOGIN).acount(),
            settings.AXES_FAILURE_LIMIT,
        )


class RegistrationTests(APITestCase):
    def course(self):
        from apps.accounts.models import College, Course, Department
        college = College.objects.get_or_create(code="T659", defaults={"name": "College"})[0]
        department = Department.objects.get_or_create(code="T659", defaults={"name": "Dept", "college": college})[0]
        return Course.objects.get_or_create(name="BS Computer Science", department=department)[0]

    def test_registering_is_recorded_against_the_new_account_with_the_role_it_asked_for(self):
        response = self.client.post(
            reverse("auth-register"), registration(PASSWORD, role_name="Student", course_id=self.course().pk), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)

        event = AuditEvent.objects.get(event_type=AuditEvent.ACCOUNT_REGISTERED)
        self.assertEqual(event.user, User.objects.get(email="newcomer@cit.edu"))
        self.assertEqual(event.metadata, {"requested_role": "Student"})

    def test_no_row_holds_the_password_or_the_activation_link_once_the_email_is_sent(self):
        self.client.post(reverse("auth-register"), registration(PASSWORD), format="json")
        for intent_id in RecoveryIntent.objects.values_list("id", flat=True):
            deliver_recovery_intent(str(intent_id))  # as the worker does after commit
        [message] = mail.outbox
        link = LINK.search(message.body)
        self.assertIsNotNone(link, message.body)

        self.assertTrue(AuditEvent.objects.filter(event_type=AuditEvent.ACCOUNT_REGISTERED).exists())
        for event in AuditEvent.objects.all():
            for secret in (PASSWORD, link.group(1), link.group(0)):
                self.assertNotIn(secret, str(event.metadata), event.event_type)

    def test_registering_with_no_role_records_none_asked_for(self):
        self.client.post(reverse("auth-register"), registration(PASSWORD), format="json")

        event = AuditEvent.objects.get(event_type=AuditEvent.ACCOUNT_REGISTERED)
        self.assertEqual(event.metadata, {"requested_role": None})

    def test_a_refused_registration_records_nothing(self):
        response = self.client.post(
            reverse("auth-register"), registration(PASSWORD, confirm="Different-1!"), format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertFalse(AuditEvent.objects.filter(event_type=AuditEvent.ACCOUNT_REGISTERED).exists())
