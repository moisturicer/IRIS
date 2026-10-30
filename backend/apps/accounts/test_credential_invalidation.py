"""
A password change ends every existing credential (ADR-045 §4, IR-642).

Tested at the authenticated HTTP boundary: sign in on two "devices", change
the password one of the two ways, and check what each device can still do.
Every token carries the account's `credential_version` as `cv`; a reset or a
change increments it, so every token minted before is refused on its next
request. A token with no `cv` or no `sid` predates the rule and is refused too.
"""

import re
import threading
from unittest.mock import patch

from django.core import mail
from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import RecoveryIntent, RecoveryToken, User, UserSession
from apps.accounts.recovery.delivery import deliver_recovery_intent

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/token/refresh/"
CHANGE = "/api/v1/auth/password/change/"
REQUEST = "/api/v1/auth/password/reset/request/"
CONFIRM = "/api/v1/auth/password/reset/confirm/"
ME = "/api/v1/users/me/"
OLD = "Original-pass-1"
NEW = "Brand-new-pass-2"


def emailed_reset_token(client, email):
    client.post(REQUEST, {"email": email}, format="json")
    for intent_id in RecoveryIntent.objects.values_list("id", flat=True):
        deliver_recovery_intent(str(intent_id))
    return re.search(r"#token=([A-Za-z0-9_-]{43})", mail.outbox[-1].body).group(1)


class CredentialTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reader@cit.edu", password=OLD,
                                             first_name="R", last_name="D", is_verified=True)

    def sign_in(self, password=OLD):
        response = APIClient().post(LOGIN, {"email": "reader@cit.edu", "password": password}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def me(self, access):
        return APIClient().get(ME, HTTP_AUTHORIZATION=f"Bearer {access}")

    def refresh(self, refresh):
        return APIClient().post(REFRESH, {"refresh": refresh}, format="json")

    def reset(self):
        token = emailed_reset_token(self.client, "reader@cit.edu")
        response = self.client.post(CONFIRM, {"token": token, "new_password": NEW,
                                              "confirm_password": NEW}, format="json")
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_reset_ends_every_device_access_and_refresh_alike(self):
        laptop, phone = self.sign_in(), self.sign_in()
        rotated = self.refresh(phone["refresh"]).json()

        self.reset()

        for tokens in (laptop, phone, rotated):
            self.assertEqual(self.me(tokens["access"]).status_code, 401)
        for refresh in (laptop["refresh"], rotated["refresh"]):
            self.assertEqual(self.refresh(refresh).status_code, 401)
        self.assertFalse(UserSession.objects.filter(user=self.user, ended_at__isnull=True).exists())

    def test_signing_in_again_with_the_new_password_works(self):
        self.reset()
        fresh = self.sign_in(NEW)
        self.assertEqual(self.me(fresh["access"]).status_code, 200)
        self.assertEqual(self.refresh(fresh["refresh"]).status_code, 200)

    def test_the_reset_issues_no_credentials_of_its_own(self):
        self.reset()
        self.assertFalse(UserSession.objects.filter(user=self.user).exists())

    def test_tokens_without_a_version_or_a_session_are_refused(self):
        legacy_access = AccessToken.for_user(self.user)
        self.assertEqual(self.me(str(legacy_access)).status_code, 401)

        signed_in = self.sign_in()
        without_cv = AccessToken(signed_in["access"])
        del without_cv["cv"]
        self.assertEqual(self.me(str(without_cv)).status_code, 401)

        legacy_refresh = RefreshToken.for_user(self.user)
        legacy_refresh["sid"] = str(UserSession.objects.get(user=self.user).pk)
        self.assertEqual(self.refresh(str(legacy_refresh)).status_code, 401)

    def test_an_authenticated_change_ends_every_session_and_every_reset_link(self):
        link = emailed_reset_token(self.client, "reader@cit.edu")
        laptop, phone = self.sign_in(), self.sign_in()

        response = self.client.post(CHANGE, {"old_password": OLD, "new_password": NEW}, format="json",
                                    HTTP_AUTHORIZATION=f"Bearer {laptop['access']}")
        self.assertEqual(response.status_code, 200, response.content)

        for tokens in (laptop, phone):
            self.assertEqual(self.me(tokens["access"]).status_code, 401)
            self.assertEqual(self.refresh(tokens["refresh"]).status_code, 401)
        self.assertIsNotNone(RecoveryToken.objects.get().revoked_at)
        stale = self.client.post(CONFIRM, {"token": link, "new_password": "Third-pass-33",
                                           "confirm_password": "Third-pass-33"}, format="json")
        self.assertEqual(stale.json()["code"], "invalid_link")
        self.assertEqual(self.me(self.sign_in(NEW)["access"]).status_code, 200)


class ResetVersusSignInRaceTests(TransactionTestCase):
    """§4: a sign-in that checked the old password cannot mint a token that
    outlives the reset racing it."""

    def setUp(self):
        self.user = User.objects.create_user(email="race@cit.edu", password=OLD,
                                             first_name="R", last_name="C", is_verified=True)

    def test_a_sign_in_with_the_old_password_never_survives_a_concurrent_reset(self):
        with patch("apps.accounts.recovery.service.enqueue"):
            token = emailed_reset_token(APIClient(), "race@cit.edu")

        for attempt in range(5):
            barrier = threading.Barrier(2)
            results = {}

            def sign_in():
                barrier.wait(10)
                results["login"] = APIClient().post(
                    LOGIN, {"email": "race@cit.edu", "password": results.get("password", OLD)}, format="json")
                connection.close()

            def reset():
                barrier.wait(10)
                with patch("apps.accounts.recovery.service.enqueue"):
                    results["reset"] = APIClient().post(
                        CONFIRM, {"token": token, "new_password": NEW, "confirm_password": NEW}, format="json")
                connection.close()

            threads = [threading.Thread(target=sign_in), threading.Thread(target=reset)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)

            self.assertEqual(results["reset"].status_code, 200, results["reset"].content)
            login = results["login"]
            if login.status_code == 200:
                access = login.json()["access"]
                me = APIClient().get(ME, HTTP_AUTHORIZATION=f"Bearer {access}")
                self.assertEqual(me.status_code, 401, f"attempt {attempt}: an old-password token survived")
            # Next round: put the old password back and issue a fresh link.
            user = User.objects.get(pk=self.user.pk)
            user.set_password(OLD)
            user.save()
            mail.outbox.clear()
            RecoveryIntent.objects.all().delete()
            from apps.accounts.models import RecoveryAttempt, RecoveryGeneration
            RecoveryAttempt.objects.all().delete()
            RecoveryGeneration.objects.all().delete()
            with patch("apps.accounts.recovery.service.enqueue"):
                token = emailed_reset_token(APIClient(), "race@cit.edu")
