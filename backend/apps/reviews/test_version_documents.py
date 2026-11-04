"""
Each version names the documents it was submitted with (ADR-058 §2, IR-872).

At the REST seam where it can be: a version records each upload slot's newest
file (nothing for an empty slot), a file uploaded between versions is "added
during" the current one and named by the next, and a file a version names, or
one that answered a document request, can't be deleted by anyone through the
API. Uploads are written through the ORM: the PDF checker is not what is under
test, and on Windows it refuses every upload.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from apps.documents.models import DocumentRequest, DocumentRequestItem, RecordUpload, UploadSlot
from apps.documents.serializers import RecordUploadSerializer
from apps.documents.services import get_next_version
from apps.records.models import Record, RecordVersion, RecordVersionDocument
from apps.reviews import routing
from core.enums import Party

from .test_new_version import NewVersionTestBase

MANILA = ZoneInfo("Asia/Manila")


def at(day, hour=12):
    return datetime(2027, 3, day, hour, tzinfo=MANILA)


def delete_url(upload):
    return reverse("record-upload-delete", args=[upload.pk])


class VersionDocumentsTestBase(NewVersionTestBase):

    def slot(self, record, name):
        return UploadSlot.objects.get_or_create(
            name=name, record_type=record.record_type, record=None,
        )[0]

    # Times are set explicitly afterwards: `RecordVersion.created_at` holds a
    # reference to `timezone.now`, so patching it would not move a version.
    def upload(self, record, slot, when):
        upload = RecordUpload.objects.create(
            record=record, slot=slot,
            file=SimpleUploadedFile(f"{slot.name}.pdf", b"%PDF-1.4 doc", content_type="application/pdf"),
            version=get_next_version(record.pk, slot.pk), uploaded_by=self.owner,
        )
        RecordUpload.objects.filter(pk=upload.pk).update(created_at=when)
        upload.refresh_from_db()
        return upload

    def dated(self, record, number, when):
        RecordVersion.objects.filter(record=record, number=number).update(created_at=when)

    def submit(self, record, when):
        """Enter review at the Adviser, which writes v1."""
        routing.enter_at_adviser(record, self.owner)
        self.dated(record, 1, when)
        record.refresh_from_db()
        return record

    def named(self, record, number):
        version = RecordVersion.objects.get(record=record, number=number)
        return list(RecordVersionDocument.objects.filter(version=version).values_list("upload_id", flat=True))

    def delete(self, upload, as_user):
        self.client.force_authenticate(as_user)
        return self.client.delete(delete_url(upload))


class WhatAVersionNamesTests(VersionDocumentsTestBase):

    def test_v1_names_each_slots_newest_upload_and_nothing_for_an_empty_slot(self):
        record = self.make_record()
        consent, approval = self.slot(record, "Consent form"), self.slot(record, "Approval sheet")
        self.upload(record, consent, at(1))
        newest = self.upload(record, consent, at(2))
        assert approval.uploads.count() == 0

        self.submit(record, at(3))

        self.assertEqual(self.named(record, 1), [newest.pk])
        self.assertFalse(RecordVersion.objects.get(record=record, number=1).documents_reconstructed)

    def test_an_upload_between_versions_is_added_during_and_named_by_the_next(self):
        record = self.make_record()
        consent = self.slot(record, "Consent form")
        first = self.upload(record, consent, at(1))
        self.submit(record, at(2))
        self.accepted_to(record, Party.IERC)
        self.opened_seat(record, Party.IERC, self.ierc)
        self.asked(record, self.ierc)
        signed = self.upload(record, consent, at(5))

        self.submitted(record)
        self.dated(record, 2, at(8))

        self.assertEqual(self.named(record, 1), [first.pk])
        self.assertEqual(self.named(record, 2), [signed.pk])
        v1, v2 = self.detail(record, self.owner)["versions"]
        self.assertEqual([d["upload_id"] for d in v1["documents"]], [first.pk])
        self.assertEqual([d["upload_id"] for d in v1["documents_added"]], [signed.pk])
        self.assertEqual([d["upload_id"] for d in v2["documents"]], [signed.pk])
        self.assertEqual(v2["documents_added"], [])
        self.assertEqual(
            {k: v1["documents"][0][k] for k in ("slot", "version")},
            {"slot": "Consent form", "version": 1},
        )
        self.assertIn(f"/documents/uploads/{first.pk}/download/", v1["documents"][0]["download_url"])

    def test_someone_who_may_not_read_the_review_gets_no_versions(self):
        record = self.make_record()
        self.upload(record, self.slot(record, "Consent form"), at(1))
        self.submit(record, at(2))

        self.assertIsNone(self.detail(record, self.ktto).get("versions"))


class DeletionTests(VersionDocumentsTestBase):

    def test_a_file_a_version_names_cant_be_deleted_by_the_owner_or_staff(self):
        record = self.make_record()
        consent = self.slot(record, "Consent form")
        self.upload(record, consent, at(1))
        named = self.upload(record, consent, at(2))
        self.submit(record, at(3))

        for user in (self.owner, self.rdco):
            with self.subTest(user=user.email):
                response = self.delete(named, user)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("v1 was submitted with this file", response.data["detail"])
        self.assertTrue(RecordUpload.objects.filter(pk=named.pk).exists())
        self.assertIn("v1 was submitted", RecordUploadSerializer(named).data["delete_refused"])

    def test_a_drafts_file_can_still_be_deleted(self):
        record = self.make_record()
        consent = self.slot(record, "Consent form")
        self.upload(record, consent, at(1))
        second = self.upload(record, consent, at(2))

        self.assertIsNone(RecordUploadSerializer(second).data["delete_refused"])
        self.assertEqual(self.delete(second, self.owner).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(RecordUpload.objects.filter(pk=second.pk).exists())

    def test_a_file_added_between_versions_can_be_deleted_until_a_version_names_it(self):
        record = self.make_record()
        consent = self.slot(record, "Consent form")
        self.upload(record, consent, at(1))
        self.submit(record, at(2))
        stray = self.upload(record, consent, at(5))

        self.assertEqual(self.delete(stray, self.owner).status_code, status.HTTP_204_NO_CONTENT)

    def test_a_file_that_answered_a_document_request_cant_be_deleted(self):
        record = self.make_record()
        consent = self.slot(record, "Consent form")
        self.upload(record, consent, at(1))
        self.submit(record, at(2))
        signed = self.upload(record, consent, at(5))
        request = DocumentRequest.objects.create(record=record, party=Party.ADVISER, message="Signed forms, please.")
        DocumentRequestItem.objects.create(request=request, slot=consent, label="Consent form", upload=signed)

        for user in (self.owner, self.rdco):
            with self.subTest(user=user.email):
                response = self.delete(signed, user)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("answered a document request", response.data["detail"])
        self.assertTrue(RecordUpload.objects.filter(pk=signed.pk).exists())

    def test_the_database_refuses_too_but_a_records_own_delete_still_cascades(self):
        """`RESTRICT`: a bug can't delete a named file, and removing a record still can."""
        from django.db.models import RestrictedError

        record = self.make_record()
        consent = self.slot(record, "Consent form")
        named = self.upload(record, consent, at(1))
        self.submit(record, at(2))

        with self.assertRaises(RestrictedError):
            RecordUpload.objects.filter(pk=named.pk).delete()
        Record.objects.filter(pk=record.pk).delete()
        self.assertFalse(RecordVersionDocument.objects.filter(upload_id=named.pk).exists())
