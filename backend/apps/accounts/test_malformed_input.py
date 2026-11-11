"""
Malformed input to the public sign-up and sign-in routes answers 400, not 500 (IR-923).

The department and course lists filter by an id from the query string, and
sign-in reads `email` and `password` from the body. All three are reachable
signed out, so a malformed value used to let anyone produce a server error.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import College, Department
from apps.audit.models import AuditEvent


class DepartmentFilterTests(APITestCase):
    def test_a_college_filter_that_is_not_a_number_is_refused(self):
        response = self.client.get(reverse("department-list"), {"college": "abc"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("college", response.json())

    def test_only_plain_digits_count_as_an_id(self):
        for value in ("1'", "1 ", "+1", "-1", "1_0", "1.0", "١"):
            with self.subTest(value=value):
                response = self.client.get(reverse("department-list"), {"college": value})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_id_too_large_for_the_column_finds_nothing(self):
        response = self.client.get(reverse("department-list"), {"college": "9" * 30})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["results"], [])

    def test_a_valid_college_filter_still_narrows_the_list(self):
        college = College.objects.filter(departments__isnull=False).first()
        self.assertIsNotNone(college, "accounts migrations should have seeded departments")

        response = self.client.get(reverse("department-list"), {"college": str(college.pk)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = response.json()["results"]
        self.assertTrue(returned)
        self.assertEqual({d["college"] for d in returned}, {college.pk})


class CourseFilterTests(APITestCase):
    def test_a_department_filter_that_is_not_a_number_is_refused(self):
        response = self.client.get(reverse("course-list"), {"department": "abc"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("department", response.json())

    def test_a_valid_department_filter_still_narrows_the_list(self):
        department = Department.objects.filter(courses__isnull=False).first()
        self.assertIsNotNone(department, "accounts migrations should have seeded courses")

        response = self.client.get(reverse("course-list"), {"department": str(department.pk)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = response.json()["results"]
        self.assertTrue(returned)
        self.assertEqual({c["department"] for c in returned}, {department.pk})


class LoginShapeTests(APITestCase):
    def login(self, body):
        return self.client.post(reverse("auth-login"), body, format="json")

    def test_an_email_and_password_that_are_not_text_are_refused_unaudited(self):
        response = self.login({"email": ["a"], "password": {"x": 1}})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(AuditEvent.objects.filter(event_type="FAILED_LOGIN").exists())

    def test_every_other_shape_that_is_not_two_text_fields_is_refused(self):
        bodies = (
            ["a", "b"],
            "a@cit.edu",
            {"email": "a@cit.edu", "password": 12345},
            {"email": 7, "password": "secret"},
            {"email": "a@cit.edu", "password": True},
        )
        for body in bodies:
            with self.subTest(body=body):
                self.assertEqual(self.login(body).status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_missing_password_is_still_an_ordinary_failed_sign_in(self):
        response = self.login({"email": "a@cit.edu"})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["detail"], "Invalid credentials.")
        self.assertTrue(AuditEvent.objects.filter(event_type="FAILED_LOGIN").exists())
