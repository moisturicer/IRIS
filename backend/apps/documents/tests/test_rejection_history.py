"""
Each rejection is kept against the upload it rejected (IR-1201, ADR-022 §3.4).

`reject_item` sends the item back to `missing`, forgets its upload and
overwrites `rejection_reason`, so before IR-1201 a second rejection lost the
first reason and nothing said which version had been rejected. Version history
now lists every upload with the rejections it received.

**Seam: the HTTP API.** The requesting party rejects through
`PATCH /document-request-items/<id>/`, and the result is read from the record
detail's `versions`. The owner's upload is made through the upload services
rather than `documents/submit/`, because the PDF check only runs on Linux and
this test is about the rejection, not the upload; `test_document_request_decisions`
covers the upload route.

Reject reasons are document-request data (ADR-022 §Amendment 5), so a reader
of the review who may not read requests gets `rejections: None`, not the reason.
"""

from django.db import transaction
from rest_framework import status

from apps.accounts.models import Role
from apps.documents.requests import resolve_item_for_upload, send_held_uploads
from apps.documents.services import create_upload
from apps.records.models import Record
from core.enums import PipelineStatus, RoleName

from .test_document_request_decisions import DecisionTestBase
from .test_document_requests import pdf

FIRST = "The signature page is missing."
SECOND = "Still unsigned on page 2."


class RejectionHistoryTests(DecisionTestBase):

    def upload_directly(self, record, item_id):
        """The owner answers `item_id`: uploads, then sends it (ADR-022 Amendment 8)."""
        with self.captureOnCommitCallbacks(execute=True), transaction.atomic():
            _, slot = resolve_item_for_upload(record, item_id)
            upload = create_upload(record, slot, pdf(), self.owner)
            send_held_uploads(record, self.owner)
        return upload

    def rejected_twice(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])
        [item] = data["items"]
        first = self.upload_directly(record, item["id"])
        self.decided(item["id"], self.ierc, "reject", FIRST)
        second = self.upload_directly(record, item["id"])
        self.decided(item["id"], self.ierc, "reject", SECOND)
        return record, first, second

    @staticmethod
    def documents_of(detail):
        """Every document Version history shows, keyed by upload id."""
        return {
            d["upload_id"]: d
            for v in detail["versions"]
            for d in [*v["documents"], *v["documents_added"]]
        }

    def test_each_rejection_stays_on_the_upload_it_rejected(self):
        record, first, second = self.rejected_twice()

        documents = self.documents_of(self.detail(record, self.owner))

        [one] = documents[first.pk]["rejections"]
        [two] = documents[second.pk]["rejections"]
        self.assertEqual(one["reason"], FIRST)
        self.assertEqual(two["reason"], SECOND)
        self.assertEqual(one["party"], "ierc")
        self.assertEqual(one["rejected_by_name"], self.ierc.get_full_name())
        self.assertLess(one["rejected_at"], two["rejected_at"])

    def test_an_upload_nobody_rejected_has_no_rejections(self):
        record = self.at_parallel_review()
        data = self.requested(record, self.ierc, [{"label": "Consent form"}])
        upload = self.upload_directly(record, data["items"][0]["id"])

        documents = self.documents_of(self.detail(record, self.owner))

        self.assertEqual(documents[upload.pk]["rejections"], [])

    def test_the_requesting_party_reads_the_rejections_too(self):
        record, first, _ = self.rejected_twice()

        documents = self.documents_of(self.detail(record, self.ierc))

        self.assertEqual(documents[first.pk]["rejections"][0]["reason"], FIRST)

    def test_a_review_reader_who_may_not_read_requests_is_not_told(self):
        """
        Someone once seated reads the review for good (IR-411), but request
        data follows participation by party (ADR-022 §Amendment 5). An ITSO
        reviewer who has since left ITSO keeps the first and loses the second.
        The paper is published so a Student can still open it.
        """
        record, first, _ = self.rejected_twice()
        Record.objects.filter(pk=record.pk).update(pipeline_status=PipelineStatus.PUBLISHED)
        self.itso.role = Role.objects.get_or_create(name=RoleName.STUDENT)[0]
        self.itso.save(update_fields=["role"])

        documents = self.documents_of(self.detail(record, self.itso))

        self.assertIsNone(documents[first.pk]["rejections"])

    def test_the_tracker_carries_the_same_rejections(self):
        record, first, _ = self.rejected_twice()

        documents = self.documents_of(self.tracker_ok(record, self.owner))

        self.assertEqual(documents[first.pk]["rejections"][0]["reason"], FIRST)

    def test_a_rejected_upload_can_no_longer_be_deleted(self):
        """Deleting it would delete the rejection's subject (ADR-058 §2's rule)."""
        record, first, _ = self.rejected_twice()
        self.client.force_authenticate(self.owner)

        response = self.client.get(f"/api/v1/documents/uploads/?record={record.pk}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        [row] = [r for r in rows if r["id"] == first.pk]
        self.assertIn("document request", row["delete_refused"])
