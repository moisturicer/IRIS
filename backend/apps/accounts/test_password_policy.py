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
        "consent_given": True,
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
                "This password is too short. It must contain at least 8 characters.",
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
                "This password is too short. It must contain at least 8 characters.",
                "This password is too common.",
                "This password is entirely numeric.",
            ]),
        )
