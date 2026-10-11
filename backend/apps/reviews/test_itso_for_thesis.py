"""IR-266 survives IR-260: a Thesis may be routed to ITSO for IP review.

Requested-office flags are hints to the Adviser, not automatic routing under
ADR-032. The create serializer must preserve a Thesis's ITSO hint, and the
Adviser can route it to the same office pool as a Project.
"""

from rest_framework import status

from apps.records.models import Record, RecordType
from apps.reviews import seats
from apps.reviews.models import RecordAssignment, RecordClearance
from core.enums import RecordTypeName

from .test_office_review import OfficeReviewTestBase


class ItsoForThesisTests(OfficeReviewTestBase):
    def submitted_through_api(self, type_name, **requested):
        self.client.force_authenticate(self.owner)
        created = self.client.post(
            "/api/v1/records/",
            {
                "title": f"ITSO route for {type_name}",
                "abstract": "A" * 40,
                "record_type": RecordType.objects.get_or_create(name=type_name)[0].pk,
                "authors": ["Test Author"],
                "adviser": self.adviser.pk,
                **requested,
            },
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        record = Record.objects.get(pk=created.data["id"])
        submitted = self.client.post(
            f"/api/v1/records/{record.pk}/submit/", {"dpa_accepted": True}, format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        self.assertEqual(record.assignments.get().party, "adviser")
        seats.open_review(record.assignments.get().seats.get(), self.adviser)
        return record

    def test_a_thesis_itso_hint_survives_create_and_itso_can_receive_it(self):
        record = self.submitted_through_api(
            RecordTypeName.THESIS_RESEARCH, requested_itso=True,
        )
        record.refresh_from_db()
        self.assertTrue(record.requested_itso)
        self.accepted_to(record, "itso")
        self.assertEqual(self.clearance(record, "itso"), "pending")
        self.client.force_authenticate(self.itso)
        queue = self.client.get("/api/v1/reviews/mine/", {"tab": "to_review"})
        self.assertEqual(queue.status_code, 200, queue.data)
        self.assertIn(record.pk, {row["record"] for row in queue.data["rows"]})

    def test_thesis_and_project_both_route_to_itso_and_ierc(self):
        for type_name in (RecordTypeName.THESIS_RESEARCH, RecordTypeName.PROJECT):
            with self.subTest(record_type=type_name):
                record = self.submitted_through_api(
                    type_name, requested_itso=True, requested_ierc=True,
                )
                self.accepted_to(record, "itso", "ierc")
                self.assertEqual(
                    set(RecordClearance.objects.filter(record=record).values_list("office", flat=True)),
                    {"itso", "ierc"},
                )
                self.opened_seat(record, "itso", self.itso)
                self.cleared(record, self.itso)
                self.assertEqual(self.clearance(record, "itso"), "cleared")
                self.assertEqual(self.clearance(record, "ierc"), "pending")

    def test_thesis_without_itso_route_has_no_itso_work(self):
        record = self.submitted_through_api(
            RecordTypeName.THESIS_RESEARCH, requested_ierc=True,
        )
        self.accepted_to(record, "ierc")
        self.assertFalse(RecordAssignment.objects.filter(record=record, party="itso").exists())
        self.assertFalse(RecordClearance.objects.filter(record=record, office="itso").exists())
