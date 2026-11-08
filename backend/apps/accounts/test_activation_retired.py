"""
The old activation links verify no one (IR-643, ADR-045 §8).

Verification links are single-use `RecoveryToken`s now. Links emailed before
that -- Django default-generator tokens, in the path (before IR-928) or the
fragment (IR-928) -- get the recovery contract's one "invalid link" answer,
which points to a new email, and change nothing. Each case uses a token that
was genuinely valid under the old scheme, so a refusal here is the retirement
and not a bad token. Log redaction stays for the old path shape, which links
still in people's inboxes keep producing.
"""
import logging

from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from apps.accounts.models import Role, RoleRequest, User
from apps.accounts.test_password_recovery import INVALID_LINK
from apps.notifications.models import Notification
from core.enums import RoleName
from core.logging import RecoveryRedaction


class RetiredActivationLinkTests(APITestCase):
    def setUp(self):
        self.rdco = Role.objects.get_or_create(name=RoleName.RDCO)[0]
        student = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        self.user = User.objects.create_user(
            email="new@cit.edu", password="pw12345!", first_name="New", last_name="Person",
            is_verified=False,
        )
        RoleRequest.objects.create(user=self.user, requested_role=student)
        self.old = {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
        }

    def assert_changed_nothing(self, response):
        self.assertEqual((response.status_code, response.json()), (400, INVALID_LINK))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_verified)
        self.assertFalse(Notification.objects.filter(broadcast_to_role=self.rdco).exists())

    def test_a_path_link_emailed_before_ir_928_verifies_no_one(self):
        self.assert_changed_nothing(self.client.get(reverse("auth-activate", kwargs={
            "uidb64": self.old["uid"], "token": self.old["token"],
        })))

    def test_a_fragment_link_emailed_by_ir_928_verifies_no_one(self):
        self.assert_changed_nothing(
            self.client.post(reverse("auth-activate-confirm"), self.old, format="json"))

    def test_any_body_gets_the_same_answer(self):
        for body in ({}, {"uid": 1}, ["x"], "x"):
            with self.subTest(body=body):
                self.assert_changed_nothing(
                    self.client.post(reverse("auth-activate-confirm"), body, format="json"))

    def test_a_stale_bearer_token_does_not_change_the_answer(self):
        self.assert_changed_nothing(self.client.post(
            reverse("auth-activate-confirm"), self.old, format="json",
            HTTP_AUTHORIZATION="Bearer expired.or.garbage",
        ))


class RedactionBackstopTests(APITestCase):
    """Old links still in inboxes keep arriving, so their paths stay redacted."""

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
