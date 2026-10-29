"""IR-635: a PIN request must not confirm a hidden Record exists."""
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.records.models import Record, RecordOwner
from apps.reviews.models import RecordAuthPin
from apps.tests.test_authorization_matrix import make_user


@pytest.mark.db_required
class PinVisibilityTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("pin-owner@cit.edu", "Student")
        cls.stranger = make_user("pin-stranger@cit.edu", "Student")
        cls.record = Record.objects.create(title="Private PIN canary", pipeline_status="draft")
        RecordOwner.objects.create(record=cls.record, user=cls.owner, is_primary=True)

    @patch("core.utils.send_email_async")
    def test_hidden_equals_missing_without_creating_a_pin_or_sending_email(self, send):
        self.client.force_authenticate(self.stranger)
        responses = [self.client.post(reverse("pin-generate"), {"record_id": pk}, format="json")
                     for pk in (self.record.pk, 2000000000)]
        self.assertEqual([r.status_code for r in responses], [404, 404])
        self.assertEqual(responses[0].content, responses[1].content)
        self.assertFalse(RecordAuthPin.objects.filter(user=self.stranger).exists())
        send.assert_not_called()

    @patch("core.utils.send_email_async")
    def test_readable_record_keeps_pin_generation(self, send):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse("pin-generate"), {"record_id": self.record.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(RecordAuthPin.objects.filter(user=self.owner, record=self.record).exists())
        send.assert_called_once()
