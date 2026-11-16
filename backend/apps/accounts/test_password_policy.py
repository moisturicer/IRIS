"""
The API enforces the configured password policy (IR-647).

`AUTH_PASSWORD_VALIDATORS` declares the policy; registration and password
change are the two ways a password enters through the API, and both must
refuse what it refuses. Driven through the HTTP endpoints only.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.tests import make_user


def registration(password, confirm=None, **extra):
    return {
        "email": "newcomer@cit.edu",
        "first_name": "New",
        "last_name": "Comer",
        "password": password,
        "confirm_password": password if confirm is None else confirm,
        # IR-789: the notice version shown (migration 0019 creates version 1)
        # and both answers, replacing the single `consent_given`.
        "notice_version": 1,
        "agree_dpa": True,
        "ai_consent": True,
        **extra,
    }


class RegistrationPasswordPolicyTests(APITestCase):
    url = reverse("auth-register")

    def test_a_common_password_is_refused_on_the_password_field(self):
        response = self.client.post(self.url, registration("password123"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This password is too common.", response.data["password"])

    def test_every_broken_rule_is_reported_together(self):
        # Seven digits: too short, too common, and entirely numeric.
        response = self.client.post(self.url, registration("1234567"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            sorted(response.data["password"]),
            sorted([
                "This password is too short. It must contain at least 12 characters.",
                "This password is too common.",
                "This password is entirely numeric.",
            ]),
        )

    def test_an_entirely_numeric_password_is_refused(self):
        response = self.client.post(self.url, registration("12345678"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This password is entirely numeric.", response.data["password"])

    def test_a_strong_password_registers(self):
        response = self.client.post(self.url, registration("Kalamansi-Tide-42"), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_a_mismatched_confirmation_is_still_reported_on_its_own_field(self):
        response = self.client.post(
            self.url, registration("Kalamansi-Tide-42", confirm="Kalamansi-Tide-43"), format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["confirm_password"], ["Passwords do not match."])


class ChangePasswordPolicyTests(APITestCase):
    url = reverse("password-change")

    def setUp(self):
        # make_user's password is set through the ORM, which no validator sees.
        self.user = make_user("changer@cit.edu")
        self.client.force_authenticate(self.user)

    def change(self, new_password, old_password="pw12345!"):
        return self.client.post(
            self.url, {"old_password": old_password, "new_password": new_password}, format="json",
        )

    def test_a_common_password_is_refused_on_the_new_password_field(self):
        response = self.change("password123")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This password is too common.", response.data["new_password"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("pw12345!"))

    def test_an_entirely_numeric_password_is_refused(self):
        response = self.change("12345678")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This password is entirely numeric.", response.data["new_password"])

    def test_a_strong_password_is_accepted(self):
        response = self.change("Kalamansi-Tide-42")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Kalamansi-Tide-42"))

    def test_a_wrong_old_password_is_still_reported_on_its_own_field(self):
        response = self.change("Kalamansi-Tide-42", old_password="not-it")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["old_password"], ["Old password is incorrect."])

    def test_every_broken_rule_is_reported_together(self):
        response = self.change("1234567")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            sorted(response.data["new_password"]),
            sorted([
                "This password is too short. It must contain at least 12 characters.",
                "This password is too common.",
                "This password is entirely numeric.",
            ]),
        )


# --- IR-819: ASVS Level 1 lengths and the breached list -------------------------

ELEVEN = "Kalamansi-T1"[:11]           # 11 characters, otherwise fine
TWELVE = "Kalamansi-T1"                 # exactly 12
TOO_LONG = "Kalamansi-Tide-" + "x" * 114  # 129 characters
BREACHED = "123456daniel"                  # in passwords/breached-12plus.txt.gz, not in Django's own list
LONG_OK = "Kalamansi-Tide-" + "x" * 113    # exactly 128


class LevelOneRegistrationTests(APITestCase):
    url = reverse("auth-register")

    def register(self, password):
        return self.client.post(self.url, registration(password), format="json")

    def test_eleven_characters_are_refused_and_twelve_register(self):
        short = self.register(ELEVEN)
        self.assertEqual(short.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This password is too short. It must contain at least 12 characters.", short.data["password"])
        self.assertEqual(self.register(TWELVE).status_code, status.HTTP_201_CREATED)

    def test_more_than_128_characters_are_refused(self):
        response = self.register(TOO_LONG)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("This password is too long. It must contain at most 128 characters.", response.data["password"])

    def test_128_characters_register(self):
        self.assertEqual(self.register(LONG_OK).status_code, status.HTTP_201_CREATED)

    def test_a_breached_password_is_refused_whatever_its_case(self):
        for password in (BREACHED, BREACHED.upper()):
            with self.subTest(password=password):
                response = self.register(password)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("This password has appeared in a data breach. Choose a different one.",
                              response.data["password"])


class LevelOneChangeTests(APITestCase):
    url = reverse("password-change")

    def setUp(self):
        self.user = make_user("level-one-changer@cit.edu")
        self.client.force_authenticate(self.user)

    def change(self, new_password):
        return self.client.post(self.url, {"old_password": "pw12345!", "new_password": new_password}, format="json")

    def test_each_rule_holds_on_a_signed_in_change(self):
        for password, message in (
            (ELEVEN, "This password is too short. It must contain at least 12 characters."),
            (TOO_LONG, "This password is too long. It must contain at most 128 characters."),
            (BREACHED, "This password has appeared in a data breach. Choose a different one."),
        ):
            with self.subTest(password=password[:20]):
                response = self.change(password)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(message, response.data["new_password"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("pw12345!"))
        self.assertEqual(self.change(TWELVE).status_code, status.HTTP_200_OK)


class LevelOneResetTests(APITestCase):
    """A reset goes through `password_errors`, which applies the same validators."""

    def test_each_rule_holds_on_a_reset(self):
        from apps.accounts.recovery.service import password_errors

        user = make_user("level-one-resetter@cit.edu")
        for password, message in (
            (ELEVEN, "This password is too short. It must contain at least 12 characters."),
            (BREACHED, "This password has appeared in a data breach. Choose a different one."),
        ):
            with self.subTest(password=password):
                self.assertIn(message, password_errors(user, password, password)["new_password"])
        self.assertIn("new_password", password_errors(user, TOO_LONG, TOO_LONG))
        self.assertEqual(password_errors(user, TWELVE, TWELVE), {})


class LevelOneResetOverHttpTests(APITestCase):
    """The breached rule at the reset endpoint itself, not only `password_errors`."""

    def test_a_reset_to_a_breached_password_is_refused_and_the_link_kept(self):
        from apps.accounts.test_credential_invalidation import CONFIRM, emailed_reset_token

        user = make_user("level-one-http@cit.edu")
        token = emailed_reset_token(self.client, user.email)
        response = self.client.post(CONFIRM, {"token": token, "new_password": BREACHED,
                                              "confirm_password": BREACHED}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("This password has appeared in a data breach. Choose a different one.",
                      response.json()["errors"]["new_password"])
        ok = self.client.post(CONFIRM, {"token": token, "new_password": TWELVE,
                                        "confirm_password": TWELVE}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
