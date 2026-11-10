"""
IR-999: soft rate limits. Each budget counts over a per-minute burst and a
daily backstop, so a person who reaches a limit waits under a minute, and
only something sending far more than heavy real use waits hours.

**Seam: the real endpoints** (the public data notice, sign-in, registration)
with the clock DRF's throttles read moved by hand.
"""

from unittest import mock

from django.core.cache import cache
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.test_lockout import PASSWORD, make_user
from apps.accounts.test_auth_throttles import rates

NOTICE = reverse("notice-current")


class Clock:
    """Stands in for `SimpleRateThrottle.timer`, which every throttle reads."""

    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class SoftLimitTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.clock = Clock()
        patcher = mock.patch.object(SimpleRateThrottle, "timer", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read_notice(self):
        return self.client.get(NOTICE)

    def assert_refused_for_under_a_minute(self, response):
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertLessEqual(int(response["Retry-After"]), 60)


class SignedOutTests(SoftLimitTests):

    def test_the_burst_refuses_for_under_a_minute_then_lets_the_address_back_in(self):
        with rates(anon_burst="2/minute", anon="99/day"):
            self.read_notice()
            self.read_notice()

            self.assert_refused_for_under_a_minute(self.read_notice())

            self.clock.advance(61)
            self.assertEqual(self.read_notice().status_code, status.HTTP_200_OK)

    def test_the_daily_backstop_still_refuses_past_its_count(self):
        with rates(anon_burst="99/minute", anon="2/day"):
            self.read_notice()
            self.clock.advance(61)
            self.read_notice()
            self.clock.advance(61)

            refused = self.read_notice()

            self.assertEqual(refused.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertGreater(int(refused["Retry-After"]), 60)


class SignedInTests(SoftLimitTests):

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(make_user("soft.limits@cit.edu"))

    def test_the_burst_refuses_for_under_a_minute_then_lets_the_person_back_in(self):
        with rates(user_burst="2/minute", user="99/day"):
            self.read_notice()
            self.read_notice()

            self.assert_refused_for_under_a_minute(self.read_notice())

            self.clock.advance(61)
            self.assertEqual(self.read_notice().status_code, status.HTTP_200_OK)

    def test_the_daily_backstop_still_refuses_past_its_count(self):
        with rates(user_burst="99/minute", user="2/day"):
            self.read_notice()
            self.clock.advance(61)
            self.read_notice()
            self.clock.advance(61)

            refused = self.read_notice()

            self.assertEqual(refused.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertGreater(int(refused["Retry-After"]), 60)


class SignInAndRegistrationTests(SoftLimitTests):

    def setUp(self):
        super().setUp()
        self.user = make_user("soft.signin@cit.edu")

    def login(self):
        return self.client.post(
            reverse("auth-login"), {"email": self.user.email, "password": PASSWORD}, format="json",
        )

    def register(self):
        return self.client.post(reverse("auth-register"), {}, format="json")

    def test_sign_in_bursts_refuse_for_under_a_minute_and_leave_registration_open(self):
        with rates(auth_login_burst="2/minute", auth_login="99/day"):
            self.login()
            self.login()

            self.assert_refused_for_under_a_minute(self.login())
            self.assertNotEqual(self.register().status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            self.clock.advance(61)
            self.assertEqual(self.login().status_code, status.HTTP_200_OK)

    def test_registration_bursts_refuse_for_under_a_minute(self):
        with rates(auth_register_burst="2/minute", auth_register="99/day"):
            self.register()
            self.register()

            self.assert_refused_for_under_a_minute(self.register())
            self.assertEqual(self.login().status_code, status.HTTP_200_OK)

    def test_sign_in_spends_none_of_the_general_burst(self):
        with rates(anon_burst="1/minute", auth_login_burst="9/minute"):
            for _ in range(3):
                self.assertEqual(self.login().status_code, status.HTTP_200_OK)


def _views():
    def walk(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns)
            elif isinstance(pattern, URLPattern):
                view = getattr(pattern.callback, "view_class", None) or getattr(pattern.callback, "cls", None)
                if view is not None:
                    yield view
    return set(walk(get_resolver().url_patterns))


def test_every_view_with_a_daily_backstop_also_has_its_burst():
    """A view that names its own throttles must not drop the burst half."""
    pairs = {"anon": "anon_burst", "user": "user_burst", "ai_query": "ai_query_burst",
             "auth_login": "auth_login_burst", "auth_register": "auth_register_burst"}
    missing = []
    for view in _views():
        scopes = {getattr(t, "scope", None) for t in getattr(view, "throttle_classes", [])}
        missing += [f"{view.__name__}: {scope} without {burst}"
                    for scope, burst in pairs.items() if scope in scopes and burst not in scopes]
    assert not missing, missing
