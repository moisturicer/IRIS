"""
An owner deletes a wrong supporting document, its first upload included (IR-1317).

ADR-058 §2: a draft's files are free to delete until the review relies on them.
The old rule refusing version 1 without an office override had no basis and is
gone. What the review relied on is still refused (`test_rejection_history`).
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.documents.models import RecordUpload, UploadSlot
from apps.records.models import Record, RecordOwner, RecordType

from .test_document_access_control import _TempMediaAPITestCase


def pdf(name="wrong.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 wrong file", content_type="application/pdf")


class FirstUploadDeletionTests(_TempMediaAPITestCase):

    def setUp(self):
        self.owner = self.make_user("owner@cit.edu")
        record_type = RecordType.objects.first()
        self.record = Record.objects.create(title="A Draft", record_type=record_type, added_by=self.owner)
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        self.slot = UploadSlot.objects.create(name="Consent Form", record_type=record_type)
        self.first = RecordUpload.objects.create(
            record=self.record, slot=self.slot, file=pdf(), uploaded_by=self.owner, version=1,
        )

    def delete(self, upload):
        self.client.force_authenticate(self.owner)
        return self.client.delete(f"/api/v1/documents/uploads/{upload.pk}/")

    def test_the_owner_deletes_the_first_upload(self):
        stored = self.first.file.name
        storage = self.first.file.storage

        response = self.delete(self.first)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RecordUpload.objects.filter(pk=self.first.pk).exists())
        self.assertFalse(storage.exists(stored))

    def test_the_first_upload_is_offered_for_removal(self):
        self.client.force_authenticate(self.owner)

        response = self.client.get(f"/api/v1/documents/uploads/?record={self.record.pk}")

        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        [row] = [r for r in rows if r["id"] == self.first.pk]
        self.assertIsNone(row["delete_refused"])

    def test_deleting_the_first_upload_leaves_later_versions(self):
        second = RecordUpload.objects.create(
            record=self.record, slot=self.slot, file=pdf("right.pdf"), uploaded_by=self.owner, version=2,
        )

        self.assertEqual(self.delete(self.first).status_code, status.HTTP_204_NO_CONTENT)

        self.assertTrue(RecordUpload.objects.filter(pk=second.pk).exists())
