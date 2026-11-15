"""
The Users page's extra columns and role filter (IR-1138): `last_login` for
Last active, the affiliation names for Unit, and `?role=` for the filter.
"""
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.records.tests import make_user


class UserListColumnTests(APITestCase):
    def setUp(self):
        self.url = reverse("user-list")
        self.client.force_authenticate(make_user("ulc_rdco@cit.edu", "RDCO"))

    def rows(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {row["email"]: row for row in response.data["results"]}

    def test_each_row_carries_last_login_and_affiliation_names(self):
        user = make_user("ulc_student@cit.edu", "Student")
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        make_user("ulc_never@cit.edu", "Student")

        rows = self.rows()

        self.assertIsNotNone(rows["ulc_student@cit.edu"]["last_login"])
        self.assertIsNone(rows["ulc_never@cit.edu"]["last_login"])
        self.assertIn("department_name", rows["ulc_student@cit.edu"])
        self.assertIn("college_name", rows["ulc_student@cit.edu"])

    def test_role_narrows_to_one_role(self):
        make_user("ulc_s@cit.edu", "Student")
        make_user("ulc_a@cit.edu", "Adviser")
        self.assertEqual(set(self.rows(role="Adviser")), {"ulc_a@cit.edu"})

    def test_office_narrows_to_the_four_office_roles(self):
        make_user("ulc_s2@cit.edu", "Student")
        make_user("ulc_itso@cit.edu", "ITSO")
        make_user("ulc_ierc@cit.edu", "IERC")
        emails = set(self.rows(role="office"))
        self.assertEqual(emails, {"ulc_rdco@cit.edu", "ulc_itso@cit.edu", "ulc_ierc@cit.edu"})
