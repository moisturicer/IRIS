"""IR-636: the manually bound analytics action retains its office gate."""
import pytest
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.tests.test_authorization_matrix import make_user


@pytest.mark.db_required
class AnalyticsAccessTests(APITestCase):
    def test_only_offices_reach_the_declared_analytics_stub(self):
        self.assertEqual(self.client.get(reverse("reviews-analytics")).status_code, 401)
        for role, expected in (("Student", 403), ("Adviser", 403), ("ITSO", 501),
                               ("IERC", 501), ("KTTO", 501), ("RDCO", 501), (None, 403)):
            with self.subTest(role=role):
                user = make_user(f"analytics-{role}@cit.edu", role, is_superuser=role is None)
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(reverse("reviews-analytics")).status_code, expected)
