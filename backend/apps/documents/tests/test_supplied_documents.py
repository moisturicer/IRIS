"""
A requested document is supplied once it is sent (ADR-022 Amendment 10, IR-1338).

The requesting party no longer accepts or rejects an upload: the item endpoint
that did (`PATCH /document-request-items/<id>/`) is gone, and a reviewer who
finds a file wrong asks again with a new request. Each reviewer of the paper
sees a supplied version as **New** (`is_new`) until they open it, which
`POST /documents/uploads/<id>/seen/` records for them alone.

**Seam: the HTTP API**, with the owner's upload stored through
`_store_slot_upload`, as `test_held_uploads` does and for its reason.
"""

from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequestItem, UploadSeen
from core.enums import DocumentRequestItemState

from .test_held_uploads import HeldUploadTestBase


class SuppliedDocumentTests(HeldUploadTestBase):

    def supplied(self):
        """IERC asks for an Ethics Clearance, and the owner sends one."""
        record = self.at_parallel_review()
        ethics = self.slot(record, "Ethics Clearance")
        data = self.requested(record, self.ierc, [{"slot": ethics.pk}])
        upload = self.stored(record, ethics)
        self.assertEqual(self.send(record).status_code, status.HTTP_200_OK)
        return record, upload, data

    def seen(self, upload, viewer):
        self.client.force_authenticate(viewer)
        return self.client.post(reverse("record-upload-seen", args=[upload.pk]), {}, format="json")

    def test_a_sent_requested_document_is_supplied_with_nothing_left_to_decide(self):
        record, upload, data = self.supplied()

        [item] = DocumentRequestItem.objects.filter(request_id=data["id"])
        self.assertEqual(item.state, DocumentRequestItemState.UPLOADED)
        self.assertEqual(item.upload_id, upload.pk)
        # The item endpoint that accepted or rejected it is gone.
        self.client.force_authenticate(self.ierc)
        refused = self.client.patch(
            f"/api/v1/document-request-items/{item.pk}/", {"action": "accept"}, format="json",
        )
        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_supplied_version_is_new_to_each_reviewer_until_they_open_it(self):
        record, upload, _ = self.supplied()

        self.assertTrue(self.slot_uploads(record, self.ierc)[upload.pk]["is_new"])
        self.assertTrue(self.slot_uploads(record, self.ktto)[upload.pk]["is_new"])

        response = self.seen(upload, self.ierc)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.slot_uploads(record, self.ierc)[upload.pk]["is_new"])
        # Another reviewer's New is their own.
        self.assertTrue(self.slot_uploads(record, self.ktto)[upload.pk]["is_new"])

    def test_opening_it_twice_keeps_one_mark(self):
        _, upload, _ = self.supplied()

        self.seen(upload, self.ierc)
        self.seen(upload, self.ierc)

        self.assertEqual(UploadSeen.objects.filter(upload=upload, user=self.ierc).count(), 1)

    def test_the_owner_never_sees_new(self):
        record, upload, _ = self.supplied()

        self.assertFalse(self.slot_uploads(record, self.owner)[upload.pk]["is_new"])

    def test_a_file_no_one_asked_for_is_not_new(self):
        record = self.at_parallel_review()
        consent = self.slot(record, "Consent Paper")
        upload = self.stored(record, consent)
        self.send(record)

        self.assertFalse(self.slot_uploads(record, self.ierc)[upload.pk]["is_new"])

    def test_someone_who_cannot_read_the_paper_gets_the_404_a_missing_file_gets(self):
        _, upload, _ = self.supplied()

        response = self.seen(upload, self.stranger)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(UploadSeen.objects.exists())
