"""
The verification link keeps its secret in the URL fragment (IR-928, ASVS 8.3.1).

A fragment is never sent by the browser, so the token stays out of server logs,
`Referer` and any proxy; the page posts it in a JSON body, as the reset page
does (ADR-045 §3). Links already emailed carry the token in the path
(`/activate/<uid>/<token>`); their GET route stays, deprecated, until those
tokens have expired.
"""
import logging
import re
from unittest import mock
from urllib.parse import parse_qs

from django.contrib.auth.tokens import default_token_generator
from django.test import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, RoleRequest, User
from apps.accounts.services import send_verification_email
from apps.notifications.models import Notification
from core.enums import RoleName
from core.logging import RecoveryRedaction

ORIGIN = "https://iris.example.edu"


def _unverified() -> User:
    return User.objects.create_user(
        email="new@cit.edu", password="pw12345!", first_name="New", last_name="Person",
        is_verified=False,
    )


def _credentials(user: User) -> dict:
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": default_token_generator.make_token(user),
    }


class VerificationEmailLinkTests(APITestCase):
    def sent_body(self, user) -> str:
        with override_settings(FRONTEND_URL=ORIGIN), \
                mock.patch("apps.accounts.services.send_email_async") as send:
            send_verification_email(user, None)
        return send.call_args.kwargs["message"]

    def test_the_link_carries_uid_and_token_in_the_fragment(self):
        user = _unverified()
        expected = _credentials(user)

        body = self.sent_body(user)

        link = re.search(r"https://\S+", body).group(0)
        base, fragment = link.split("#", 1)
        self.assertEqual(base, f"{ORIGIN}/activate")
        fields = {k: v[0] for k, v in parse_qs(fragment).items()}
        self.assertEqual(fields, expected)

    def test_nothing_secret_is_in_the_path_or_query(self):
        user = _unverified()
        credentials = _credentials(user)

        body = self.sent_body(user)

        before_fragment = re.search(r"https://[^\s#]+", body).group(0)
        self.assertNotIn(credentials["token"], before_fragment)
        self.assertNotIn(credentials["uid"], before_fragment)
        self.assertNotIn("/activate/", before_fragment)
        self.assertNotIn("?", before_fragment)

    def test_the_link_in_the_email_verifies_the_account_through_the_body_endpoint(self):
        user = _unverified()
        body = self.sent_body(user)
        fragment = re.search(r"#(\S+)", body).group(1)
        fields = {k: v[0] for k, v in parse_qs(fragment).items()}

        response = self.client.post(reverse("auth-activate-confirm"), fields, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)


class ActivateConfirmTests(APITestCase):
    url = property(lambda self: reverse("auth-activate-confirm"))

    def setUp(self):
        self.rdco = Role.objects.get_or_create(name=RoleName.RDCO)[0]
        self.student = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        self.user = _unverified()
        RoleRequest.objects.create(user=self.user, requested_role=self.student)

    def post(self, data):
        return self.client.post(self.url, data, format="json")

    def test_a_valid_body_verifies_and_notifies_rdco_once(self):
        response = self.post(_credentials(self.user))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"detail": "Account activated."})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)
        self.assertEqual(Notification.objects.filter(broadcast_to_role=self.rdco).count(), 1)

    def test_repeating_it_is_still_a_success_and_notifies_nobody_again(self):
        credentials = _credentials(self.user)
        for _ in range(3):
            self.assertEqual(self.post(credentials).status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(broadcast_to_role=self.rdco).count(), 1)

    def test_a_wrong_token_verifies_nobody(self):
        response = self.post({**_credentials(self.user), "token": "abc123-0123456789abcdef"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {"detail": "Invalid or expired link."})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    def test_an_unknown_uid_is_the_same_refusal(self):
        response = self.post({**_credentials(self.user), "uid": "!!!"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {"detail": "Invalid or expired link."})

    def test_a_body_that_is_not_two_strings_is_the_same_refusal(self):
        valid = _credentials(self.user)
        for body in (
            {}, {"uid": valid["uid"]}, {"token": valid["token"]},
            {"uid": 1, "token": valid["token"]}, {"uid": valid["uid"], "token": ["x"]},
            {"uid": None, "token": None}, ["uid", "token"], "uid",
        ):
            with self.subTest(body=body):
                response = self.post(body)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.json(), {"detail": "Invalid or expired link."})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    def test_the_secret_in_the_query_string_is_ignored(self):
        credentials = _credentials(self.user)
        response = self.client.post(
            f"{self.url}?uid={credentials['uid']}&token={credentials['token']}", {}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)

    def test_get_is_not_allowed_on_the_body_endpoint(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_the_answer_is_never_cached_or_sent_on_as_a_referrer(self):
        response = self.post(_credentials(self.user))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_it_needs_no_sign_in(self):
        self.assertEqual(self.post(_credentials(self.user)).status_code, status.HTTP_200_OK)


class LegacyPathLinkTests(APITestCase):
    """Emails sent before IR-928 link to `/activate/<uid>/<token>`; they keep working."""

    def test_a_link_emailed_before_the_change_still_verifies(self):
        user = _unverified()
        credentials = _credentials(user)

        response = self.client.get(reverse("auth-activate", kwargs={
            "uidb64": credentials["uid"], "token": credentials["token"],
        }))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)

    def test_the_old_route_has_the_old_shape(self):
        self.assertEqual(reverse("auth-activate", kwargs={"uidb64": "a", "token": "b"}),
                         "/api/v1/auth/activate/a/b/")


class RedactionBackstopTests(APITestCase):
    """Log redaction stays for the legacy path (and anything that still sends one)."""

    def redacted(self, message: str) -> str:
        record = logging.LogRecord("django.request", logging.INFO, __file__, 1, message, (), None)
        RecoveryRedaction().filter(record)
        return record.getMessage()

    def test_a_legacy_activation_path_is_redacted(self):
        line = self.redacted("GET /activate/MQ/abc123-0123456789abcdef HTTP/1.1")
        self.assertNotIn("abc123", line)
        self.assertIn("/activate/[redacted]", line)

    def test_a_legacy_api_activation_path_is_redacted(self):
        line = self.redacted("Not Found: /api/v1/auth/activate/MQ/abc123-0123456789abcdef/")
        self.assertNotIn("abc123", line)

    def test_other_lines_are_untouched(self):
        self.assertEqual(self.redacted("GET /api/v1/records/ 200"), "GET /api/v1/records/ 200")
