"""
IR-661: login and registration each have a rate limit of their own.

The general anonymous budget is too loose to stop guessing and too tight for a
shared campus network. Each budget belongs to one client address, read the way
the lockout reads it (IR-656), so a forged `X-Forwarded-For` buys no new budget.

**Seam: the real endpoints**, with the headers production's proxies send.
"""

from unittest import mock

from axes.models import AccessAttempt
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.test_client_address import ALICE, MALLORY, behind_proxies
from apps.accounts.lockout import TOO_MANY_ATTEMPTS
from apps.accounts.test_lockout import PASSWORD, make_user


def rates(**scopes):
    """The configured rates with `scopes` replaced, for one test."""
    return mock.patch.object(
        SimpleRateThrottle,
        "THROTTLE_RATES",
        {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], **scopes},
    )


class AuthEndpoints(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = make_user("throttled.reader@cit.edu")

    def login(self, password=PASSWORD, **extra):
        return self.client.post(
            reverse("auth-login"), {"email": self.user.email, "password": password}, format="json", **extra,
        )

    def register(self, **extra):
        """A refused body still spends budget, so this needs no valid signup."""
        return self.client.post(reverse("auth-register"), {}, format="json", **extra)


class EachScopeStandsAloneTests(AuthEndpoints):

    def test_exhausting_login_answers_429_and_leaves_registration_open(self):
        with rates(auth_login="2/hour", auth_register="2/hour"):
            self.assertEqual(self.login().status_code, status.HTTP_200_OK)
            self.assertEqual(self.login().status_code, status.HTTP_200_OK)

            refused = self.login()

            self.assertEqual(refused.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertGreater(int(refused["Retry-After"]), 0)
            self.assertNotEqual(self.register().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_exhausting_registration_answers_429_and_leaves_login_open(self):
        with rates(auth_login="2/hour", auth_register="2/hour"):
            self.register()
            self.register()

            refused = self.register()

            self.assertEqual(refused.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertGreater(int(refused["Retry-After"]), 0)
            self.assertEqual(self.login().status_code, status.HTTP_200_OK)

    def test_neither_endpoint_spends_the_general_anonymous_budget(self):
        with rates(anon="1/day", auth_login="9/hour", auth_register="9/hour"):
            for _ in range(3):
                self.assertEqual(self.login().status_code, status.HTTP_200_OK)
                self.assertNotEqual(self.register().status_code, status.HTTP_429_TOO_MANY_REQUESTS)


@override_settings(TRUSTED_PROXY_COUNT=2)
class ClientAddressTests(AuthEndpoints):

    def test_a_forged_forwarded_address_buys_no_new_budget(self):
        with rates(auth_login="1/hour"):
            self.assertEqual(
                self.login(**behind_proxies(MALLORY, forged="1.1.1.1")).status_code, status.HTTP_200_OK,
            )

            refused = self.login(**behind_proxies(MALLORY, forged="2.2.2.2"))

            self.assertEqual(refused.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_one_clients_exhausted_budget_does_not_block_another(self):
        with rates(auth_login="1/hour"):
            self.login(**behind_proxies(MALLORY))
            self.assertEqual(
                self.login(**behind_proxies(MALLORY)).status_code, status.HTTP_429_TOO_MANY_REQUESTS,
            )

            self.assertEqual(self.login(**behind_proxies(ALICE)).status_code, status.HTTP_200_OK)


class LockoutIsUnaffectedTests(AuthEndpoints):

    def test_the_axes_lockout_still_answers_with_its_own_code(self):
        with rates(auth_login="99/hour"):
            for _ in range(settings.AXES_FAILURE_LIMIT):
                response = self.login(password="wrong")

            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertEqual(response.json()["code"], TOO_MANY_ATTEMPTS)

    def test_a_throttled_attempt_counts_no_failure_against_the_account(self):
        with rates(auth_login="1/hour"):
            self.login(password="wrong")
            self.assertEqual(self.login(password="wrong").status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            self.assertEqual(AccessAttempt.objects.get(username=self.user.email).failures_since_start, 1)
