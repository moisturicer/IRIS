"""
IR-656: the login lockout counts the real client, not nginx.

Behind nginx `REMOTE_ADDR` is nginx, and axes keys its lock on username + IP. So
a stranger guessing at an account locked its owner out from every address, and
the address recorded was useless. The client's address is the entry the trusted
proxies wrote in `X-Forwarded-For`, counted from the right; anything to its left
came from the client and can be anything.

**Seam: the real login endpoint**, with the headers production's proxies send.
"""

import os
import subprocess
import sys
from pathlib import Path

from axes.models import AccessAttempt
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.test_lockout import make_user

NGINX = "172.18.0.9"
TLS_PROXY = "10.0.0.5"
ALICE = "203.0.113.10"
MALLORY = "198.51.100.66"
BACKEND = Path(__file__).resolve().parents[2]


def behind_proxies(client_address, forged=""):
    """What Django receives through the TLS proxy and nginx."""
    prefix = f"{forged}, " if forged else ""
    return {
        "REMOTE_ADDR": NGINX,
        "HTTP_X_FORWARDED_FOR": f"{prefix}{client_address}, {TLS_PROXY}",
    }


class LoginAttempts(APITestCase):
    def setUp(self):
        self.user = make_user("client.address@cit.edu")
        self.url = reverse("auth-login")

    def attempt(self, password="wrong", **extra):
        return self.client.post(
            self.url, {"email": self.user.email, "password": password}, format="json", **extra,
        )

    def lock_out(self, **extra):
        for _ in range(settings.AXES_FAILURE_LIMIT):
            response = self.attempt(**extra)
        self.assertEqual(response.status_code, 429)


@override_settings(TRUSTED_PROXY_COUNT=2)
class BehindTwoProxiesTests(LoginAttempts):

    def test_a_stranger_guessing_does_not_lock_the_owner_out(self):
        self.lock_out(**behind_proxies(MALLORY))

        self.assertEqual(self.attempt(**behind_proxies(ALICE)).status_code, 401)

    def test_the_attempt_records_the_client_not_a_proxy(self):
        self.attempt(**behind_proxies(MALLORY))

        self.assertEqual(AccessAttempt.objects.get().ip_address, MALLORY)

    def test_a_forged_entry_cannot_escape_the_lock(self):
        self.lock_out(**behind_proxies(MALLORY))

        for forged in ("1.2.3.4", "8.8.8.8, 9.9.9.9", "not-an-address"):
            with self.subTest(forged=forged):
                response = self.attempt(**behind_proxies(MALLORY, forged=forged))
                self.assertEqual(response.status_code, 429)

    def test_a_forged_entry_cannot_lock_someone_else_out(self):
        self.lock_out(**behind_proxies(MALLORY, forged=ALICE))

        self.assertEqual(self.attempt(**behind_proxies(ALICE)).status_code, 401)

    def test_too_few_entries_fall_back_to_the_direct_peer(self):
        self.attempt(REMOTE_ADDR=NGINX, HTTP_X_FORWARDED_FOR=TLS_PROXY)

        self.assertEqual(AccessAttempt.objects.get().ip_address, NGINX)

    def test_a_malformed_trusted_entry_falls_back_to_the_direct_peer(self):
        self.attempt(REMOTE_ADDR=NGINX, HTTP_X_FORWARDED_FOR=f"not-an-address, {TLS_PROXY}")

        self.assertEqual(AccessAttempt.objects.get().ip_address, NGINX)


@override_settings(TRUSTED_PROXY_COUNT=0)
class WithNoTrustedProxyTests(LoginAttempts):

    def test_the_header_is_ignored(self):
        self.attempt(REMOTE_ADDR=ALICE, HTTP_X_FORWARDED_FOR=MALLORY)

        self.assertEqual(AccessAttempt.objects.get().ip_address, ALICE)


class ProductionSettingTests(APITestCase):
    """The count is a fact about the deployment, so production will not guess it."""

    def load_production(self, **extra):
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "DEBUG": "False",
            "ALLOWED_HOSTS": "testserver",
            "CORS_ALLOWED_ORIGINS": "https://iris.example.edu",
            # Recovery transport (IR-642) is required in production too.
            "FRONTEND_URL": "https://iris.example.edu",
            "EMAIL_HOST": "smtp.example.edu",
            "EMAIL_HOST_USER": "iris@example.edu",
            "EMAIL_HOST_PASSWORD": "test-only",
        }
        env.pop("TRUSTED_PROXY_COUNT", None)
        env.update(extra)
        return subprocess.run(
            [sys.executable, "-c", "import django; django.setup()"],
            cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
        )

    def test_production_refuses_to_start_without_the_count(self):
        done = self.load_production()
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("TRUSTED_PROXY_COUNT", done.stderr)

    def test_production_refuses_a_count_of_zero(self):
        done = self.load_production(TRUSTED_PROXY_COUNT="0")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("TRUSTED_PROXY_COUNT", done.stderr)

    def test_production_starts_with_a_count(self):
        done = self.load_production(TRUSTED_PROXY_COUNT="2")
        self.assertEqual(done.returncode, 0, done.stderr[-1500:])
