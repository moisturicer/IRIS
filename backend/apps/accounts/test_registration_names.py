"""Registration identity rules through the REST boundary (IR-857)."""
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import Role, RoleRequest, User
from apps.accounts.test_password_policy import registration
from apps.accounts.tests import make_user


class RegistrationNamesTests(APITestCase):
    def test_invalid_names_return_field_errors_without_creating_anything(self):
        Role.objects.get_or_create(name="Student")
        for field, label in [("first_name", "First name"), ("last_name", "Last name")]:
            for value in ["", "  ", "Ana3", "123", "---", "@#$", "\u0301", "Ana🙂", None, [], {}]:
                with self.subTest(field=field, value=value):
                    users, requests = User.objects.count(), RoleRequest.objects.count()
                    response = self.client.post(
                        reverse("auth-register"),
                        registration("Kalamansi-Tide-42", role_name="Student", course_id=999, **{field: value}),
                        format="json",
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)
                    self.assertIn(label, str(response.data[field]))
                    self.assertEqual(User.objects.count(), users)
                    self.assertEqual(RoleRequest.objects.count(), requests)

    def test_missing_names_are_required(self):
        payload = registration("Kalamansi-Tide-42")
        del payload["first_name"], payload["last_name"]
        response = self.client.post(reverse("auth-register"), payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("First name", str(response.data["first_name"]))
        self.assertIn("Last name", str(response.data["last_name"]))
        self.assertFalse(User.objects.filter(email=payload["email"]).exists())

    def test_unicode_multipart_names_trim_only_edges_and_preserve_existing_accounts(self):
        existing = make_user("existing@cit.edu", middle_initial="P.")
        self.client.force_authenticate(existing)
        before = self.client.get(reverse("user-me")).data
        self.client.force_authenticate(None)
        response = self.client.post(
            reverse("auth-register"),
            registration("Kalamansi-Tide-42", first_name="  Jose\u0301 李  Anne-Marie  ", last_name="  D’Arcy O'Neill  "),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["first_name"], "Jose\u0301 李  Anne-Marie")
        self.assertEqual(response.data["last_name"], "D’Arcy O'Neill")
        self.client.force_authenticate(existing)
        after = self.client.get(reverse("user-me")).data
        for field in ["first_name", "middle_initial", "last_name"]:
            self.assertEqual(after[field], before[field])
        self.assertEqual(after["middle_initial"], "P.")
        existing.refresh_from_db()
        self.assertEqual(existing.get_full_name(), "Test P. User")
