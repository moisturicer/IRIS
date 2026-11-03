"""
Users in Django's admin site (ADR-051 §5-6, amended 2026-11-03, IR-781).

The System Admin role is given only here, by a Django superuser, and never
through IRIS's API. A System Admin is a named person's account and not a
Django superuser, so the form refuses the role together with either flag.
"""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, User
from core.enums import RoleName

PASSWORD = "Kalamansi-Tide-42"


class DjangoAdminUsersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(email="dj-super@cit.edu", password=PASSWORD)
        cls.system_admin = Role.objects.get(name=RoleName.SYSTEM_ADMIN)
        cls.itso = Role.objects.get(name=RoleName.ITSO)
        cls.person = User.objects.create_user(
            email="dj-person@cit.edu", password=PASSWORD, first_name="Ana", last_name="Cruz",
            is_verified=True, role=Role.objects.get(name=RoleName.STUDENT),
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def _change(self, user, **fields):
        data = {
            "email": user.email, "first_name": user.first_name, "middle_initial": user.middle_initial or "",
            "last_name": user.last_name, "role": user.role_id or "",
            "is_verified": "on" if user.is_verified else "", "is_active": "on" if user.is_active else "",
            "is_locked": "", "is_office_coordinator": "on" if user.is_office_coordinator else "",
        }
        data.update(fields)
        return self.client.post(reverse("admin:accounts_user_change", args=[user.pk]), {
            key: value for key, value in data.items() if value != ""
        })

    def test_a_superuser_lists_users(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dj-person@cit.edu")

    def test_a_superuser_adds_a_named_person_as_system_admin_and_they_are_not_a_superuser(self):
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "email": "dj-new-admin@cit.edu", "first_name": "Rosa", "last_name": "Diaz",
            "role": self.system_admin.pk, "password1": PASSWORD, "password2": PASSWORD,
        })

        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and
                         response.context["adminform"].form.errors)
        made = User.objects.get(email="dj-new-admin@cit.edu")
        self.assertEqual(made.role, self.system_admin)
        self.assertFalse(made.is_superuser)
        self.assertFalse(made.is_staff)
        self.assertTrue(made.check_password(PASSWORD))

    def test_a_superuser_gives_an_existing_user_the_role(self):
        response = self._change(self.person, role=self.system_admin.pk)

        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual(self.person.role, self.system_admin)

    def test_the_role_is_refused_together_with_either_flag(self):
        for flag in ("is_superuser", "is_staff"):
            with self.subTest(flag=flag):
                response = self._change(self.person, role=self.system_admin.pk, **{flag: "on"})

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
                self.person.refresh_from_db()
                self.assertNotEqual(self.person.role, self.system_admin)
                self.assertFalse(getattr(self.person, flag))

    def test_a_role_change_here_drops_the_coordinator_flag_as_every_role_change_does(self):
        User.objects.filter(pk=self.person.pk).update(role=self.itso, is_office_coordinator=True)
        self.person.refresh_from_db()

        self._change(self.person, role=Role.objects.get(name=RoleName.IERC).pk, is_office_coordinator="on")

        self.person.refresh_from_db()
        self.assertEqual(self.person.role.name, RoleName.IERC)
        self.assertFalse(self.person.is_office_coordinator)
