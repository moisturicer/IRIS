"""
Registration accepts only the institution's email domains (IR-660).

`REGISTRATION_EMAIL_DOMAINS` lists them. Matching is exact and ignores case, so
a look-alike that merely contains the domain is refused. Empty accepts any
domain, which only development allows: production refuses to start without it,
checked in CI's "production settings boot" step. Existing accounts, seed_demo's
among them, are never re-checked, because the rule lives in registration only.
"""

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import DataNotice, User
from apps.accounts.tests import make_user
from config.settings.base import email_domains

PASSWORD = "pw12345!"


class RegistrationEmailDomainTests(APITestCase):
    url = reverse("auth-register")

    def register(self, email):
        return self.client.post(self.url, {
            "email": email, "first_name": "New", "last_name": "Comer",
            "password": "Kalamansi-Tide-42", "confirm_password": "Kalamansi-Tide-42",
            "notice_version": DataNotice.current().number, "agree_dpa": True, "ai_consent": True,
        }, format="json")

    @override_settings(REGISTRATION_EMAIL_DOMAINS=["cit.edu"])
    def test_the_institutions_domain_registers_whatever_its_case(self):
        for email in ("juan@cit.edu", "Maria@CIT.EDU"):
            with self.subTest(email=email):
                response = self.register(email)
                self.assertEqual(response.status_code, 201, response.content)

    @override_settings(REGISTRATION_EMAIL_DOMAINS=["cit.edu"])
    def test_any_other_domain_is_refused_on_the_email_field_naming_the_domain(self):
        for email in (
            "juan@gmail.com",
            "juan@cit.edu.evil.com",  # contains the domain, isn't it
            "juan@evilcit.edu",       # ends with it, isn't it
            "juan@mail.cit.edu",      # a subdomain is a different domain
        ):
            with self.subTest(email=email):
                response = self.register(email)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(
                    response.json()["email"],
                    ["Register with your institutional email address, ending in @cit.edu."],
                )
                self.assertFalse(User.objects.filter(email__iexact=email).exists())

    @override_settings(REGISTRATION_EMAIL_DOMAINS=["cit.edu", "cit-u.edu.ph"])
    def test_several_domains_are_all_accepted_and_all_named(self):
        self.assertEqual(self.register("ana@cit-u.edu.ph").status_code, 201)
        refused = self.register("ana@example.com")
        self.assertEqual(
            refused.json()["email"],
            ["Register with your institutional email address, ending in @cit.edu or @cit-u.edu.ph."],
        )

    @override_settings(REGISTRATION_EMAIL_DOMAINS=[])
    def test_empty_accepts_any_domain_as_development_may(self):
        self.assertEqual(self.register("tester@example.com").status_code, 201)

    @override_settings(REGISTRATION_EMAIL_DOMAINS=["cit.edu"])
    def test_an_existing_account_outside_the_domain_still_signs_in(self):
        make_user("legacy@example.com", None)
        response = APIClient().post(
            "/api/v1/auth/login/", {"email": "legacy@example.com", "password": PASSWORD}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)


class DomainSettingTests(SimpleTestCase):
    def test_domains_are_read_lower_case_without_a_leading_at(self):
        self.assertEqual(email_domains(" CIT.edu, @cit-u.edu.ph ,"), ["cit.edu", "cit-u.edu.ph"])

    def test_an_unset_setting_is_empty(self):
        self.assertEqual(email_domains(""), [])
