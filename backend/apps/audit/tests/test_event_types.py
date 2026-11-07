from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditEvent
from apps.audit.tests.test_immutability import make_user
from core.enums import RoleName

EVENT_TYPES = "/api/v1/audit/event-types/"


class AuditEventTypesTests(APITestCase):
    """IR-913: the filter's options come from the API, so a new type needs no frontend change."""

    def setUp(self):
        self.client.force_authenticate(make_user("types-reader@cit.edu", RoleName.SYSTEM_ADMIN))

    def test_lists_every_event_type_with_its_label_in_the_models_order(self):
        response = self.client.get(EVENT_TYPES)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            [{"type": value, "label": label} for value, label in AuditEvent.EVENT_TYPE_CHOICES],
        )

    def test_a_type_added_to_the_choices_is_listed_without_any_other_change(self):
        # The point of the endpoint: the list is read from the choices at request
        # time, not copied from them. Adding one here must show up in the response.
        added = ("A_BRAND_NEW_EVENT", "A Brand New Event")
        with patch.object(AuditEvent, "EVENT_TYPE_CHOICES", [*AuditEvent.EVENT_TYPE_CHOICES, added]):
            listed = {row["type"]: row["label"] for row in self.client.get(EVENT_TYPES).json()}

        self.assertEqual(listed["A_BRAND_NEW_EVENT"], "A Brand New Event")

    def test_every_listed_type_is_accepted_by_the_logs_own_filter(self):
        # The two endpoints must agree: an option the filter offers can never be
        # one the log then refuses with a 400.
        for row in self.client.get(EVENT_TYPES).json():
            with self.subTest(type=row["type"]):
                self.assertEqual(
                    self.client.get("/api/v1/audit/", {"event_type": row["type"]}).status_code,
                    status.HTTP_200_OK,
                )

    def test_the_list_is_not_paginated(self):
        body = self.client.get(EVENT_TYPES, {"page_size": 1}).json()

        self.assertIsInstance(body, list)
        self.assertEqual(len(body), len(AuditEvent.EVENT_TYPE_CHOICES))

    def test_an_anonymous_request_is_refused(self):
        self.client.force_authenticate(user=None)

        self.assertIn(
            self.client.get(EVENT_TYPES).status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
