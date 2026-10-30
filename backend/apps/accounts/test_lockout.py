"""
A locked sign-in says which lock it is, and when it lifts (IR-555).

There are two server locks. django-axes refuses a user and IP after
`AXES_FAILURE_LIMIT` failures and lets them back after `AXES_COOLOFF_TIME`;
RDCO's manual lock (`User.is_locked`) never lifts on its own. The sign-in
screen used to describe both as "try again in 15:00". The server now says
which one it is, with `code`, and gives `unlock_at` only for the one that
actually ends.
"""
from datetime import timedelta
from unittest import mock

from axes.models import AccessAttempt
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User

PASSWORD = "Correct-horse-1!"

# Axes reads the clock in one place, stamping `request.axes_attempt_time`, and
# measures every cool-off from that stamp; moving it moves time for axes alone.
AXES_CLOCK = "axes.handlers.proxy.now"


def make_user(email, **extra):
    extra.setdefault("is_verified", True)
    return User.objects.create_user(
        email=email, password=PASSWORD, first_name="Test", last_name="User",
        role=Role.objects.get_or_create(name="Student")[0], **extra,
    )


class AxesLockoutTests(APITestCase):
    def setUp(self):
        self.user = make_user("locked.out@cit.edu")
        self.url = reverse("auth-login")

    def attempt(self, password):
        return self.client.post(self.url, {"email": self.user.email, "password": password}, format="json")

    def lock_out(self):
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.assertEqual(self.attempt("wrong").status_code, status.HTTP_401_UNAUTHORIZED)
        return self.attempt("wrong")

    def test_the_lockout_reply_is_json_naming_the_lock_and_when_it_lifts(self):
        response = self.lock_out()

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        body = response.json()
        self.assertEqual(body["code"], "too_many_attempts")
        self.assertTrue(body["detail"])

        # Axes counts an attempt while its latest failure is within the
        # cool-off, so the lock lifts one cool-off after that failure.
        latest = AccessAttempt.objects.get(username=self.user.email).attempt_time
        self.assertEqual(parse_datetime(body["unlock_at"]), latest + settings.AXES_COOLOFF_TIME)

    def test_a_refused_attempt_during_the_lock_moves_unlock_at_with_it(self):
        first = parse_datetime(self.lock_out().json()["unlock_at"])
        later = timezone.now() + timedelta(seconds=30)

        with mock.patch(AXES_CLOCK, return_value=later):
            response = self.attempt(PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        latest = AccessAttempt.objects.get(username=self.user.email).attempt_time
        self.assertEqual(parse_datetime(response.json()["unlock_at"]), latest + settings.AXES_COOLOFF_TIME)
        self.assertGreaterEqual(parse_datetime(response.json()["unlock_at"]), first)

    def test_axes_admits_the_next_attempt_after_unlock_at(self):
        unlock_at = parse_datetime(self.lock_out().json()["unlock_at"])

        with mock.patch(AXES_CLOCK, return_value=unlock_at + timedelta(seconds=1)):
            response = self.attempt(PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_axes_still_refuses_just_before_unlock_at(self):
        unlock_at = parse_datetime(self.lock_out().json()["unlock_at"])

        with mock.patch(AXES_CLOCK, return_value=unlock_at - timedelta(seconds=1)):
            response = self.attempt(PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class AsgiLockoutTests(APITestCase):
    """
    Production serves Django over ASGI, where axes' middleware runs its async
    branch and calls the lockout callable with a different argument list. The
    async client goes through that branch.
    """

    async def test_the_lockout_reply_carries_unlock_at_under_asgi_too(self):
        from asgiref.sync import sync_to_async

        user = await sync_to_async(make_user)("asgi.locked@cit.edu")
        url = reverse("auth-login")
        body = {"email": user.email, "password": "wrong"}

        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            await self.async_client.post(url, body, content_type="application/json")
        response = await self.async_client.post(url, body, content_type="application/json")

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        attempt = await AccessAttempt.objects.aget(username=user.email)
        self.assertEqual(
            parse_datetime(response.json()["unlock_at"]),
            attempt.attempt_time + settings.AXES_COOLOFF_TIME,
        )


class ManualLockTests(APITestCase):
    def test_a_manually_locked_account_is_told_so_with_no_unlock_time(self):
        user = make_user("held@cit.edu", is_locked=True)

        response = self.client.post(
            reverse("auth-login"), {"email": user.email, "password": PASSWORD}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {"detail": "Account is locked.", "code": "locked_by_admin"})
