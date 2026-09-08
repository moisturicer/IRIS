"""
IR-153: object-level authorization on the `documents/` endpoints.

Six endpoints resolved a record straight from a request parameter and never
asked whether the caller had any claim on it. `IsAuthenticated` was the whole
gate, so any verified account -- every student in the university -- could read,
download or write into any other record's documents:

* `POST   /documents/submit/`                     upload a PDF into someone else's record
* `GET    /documents/records/<id>/slots/`         read their upload history
* `GET    /documents/uploads/?record=<id>`        list their uploads
* `POST   /documents/uploads/create/`             upload a new version into their record
* `GET    /documents/files/?record=<id>`          list their supplementary files
* `GET    /documents/files/download-all/?record=` **ZIP up and download all of them**

The last one is the sharpest: it needed only a record id in a query string.

`DocumentDownloadPermissionTests` in `test_document_access_control.py` already
covers the two endpoints that *did* check (upload download and delete). This
module covers the six that did not, and asserts the rule is the same one --
owner or office staff -- rather than a second, subtly different rule per view.

Note the deliberate asymmetry with `RecordVisibilityTests`: a refused *record*
returns 404 so the API does not confirm the record exists, while a refused
*document* endpoint returns 403. That is the acceptance criteria's own split,
and it is coherent -- the caller supplied the record id here, so they already
know it exists; withholding the documents is the whole job.
"""

import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.documents.models import RecordFile, RecordUpload, UploadSlot
from apps.records.models import Record, RecordOwner, RecordType


class RecordDocumentAuthorizationTests(APITestCase):
    """Owner and office staff may reach a record's documents. Nobody else may."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Same lifecycle pairing as test_document_access_control.py: creating
        # the temp dir in a decorator argument would leave one behind on mere
        # import, whether or not a test ran.
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    @staticmethod
    def make_user(email, role_name=None):
        role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
        return User.objects.create_user(
            email=email, password="TestPass123!", first_name="Test",
            last_name="User", role=role, is_verified=True,
        )

    def setUp(self):
        self.owner    = self.make_user("doc-owner@cit.edu", "Student")
        self.stranger = self.make_user("doc-stranger@cit.edu", "Student")
        self.rdco     = self.make_user("doc-rdco@cit.edu", "RDCO")

        # Reuse a seeded RecordType rather than creating one: accounts/0003
        # seeds reference rows with explicit ids and leaves the Postgres
        # sequence at 1, so create() raises duplicate-pkey (IR-126).
        self.record_type = RecordType.objects.first()
        self.assertIsNotNone(self.record_type, "no seeded RecordType -- migrations incomplete")

        self.record = Record.objects.create(
            title="Confidential Disclosure", abstract="D" * 40,
            record_type=self.record_type, added_by=self.owner,
            pipeline_status="draft",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)

        self.slot = UploadSlot.objects.create(name="Manuscript", record_type=self.record_type)
        self.upload = RecordUpload.objects.create(
            record=self.record, slot=self.slot,
            file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.4 secret", content_type="application/pdf"),
            uploaded_by=self.owner,
        )
        RecordFile.objects.create(
            record=self.record,
            file=SimpleUploadedFile("appendix.txt", b"secret appendix"),
        )

    # --- helpers ---------------------------------------------------------

    def _pdf(self):
        return SimpleUploadedFile("new.pdf", b"%PDF-1.4 x", content_type="application/pdf")

    def _submit(self):
        # Patch the Celery dispatch: the broker is not running under test, and
        # this asserts authorization, not ingestion.
        with mock.patch("apps.documents.tasks.extract_pdf_text.delay"):
            return self.client.post(
                "/api/v1/documents/submit/",
                {"record": self.record.pk, "slot": self.slot.pk, "file": self._pdf()},
                format="multipart",
            )

    def _upload_create(self):
        return self.client.post(
            "/api/v1/documents/uploads/create/",
            {"record": self.record.pk, "slot": self.slot.pk, "file": self._pdf()},
            format="multipart",
        )

    def _slots(self):
        return self.client.get(f"/api/v1/documents/records/{self.record.pk}/slots/")

    def _uploads(self):
        return self.client.get(f"/api/v1/documents/uploads/?record={self.record.pk}")

    def _files(self):
        return self.client.get(f"/api/v1/documents/files/?record={self.record.pk}")

    def _download_all(self):
        return self.client.get(f"/api/v1/documents/files/download-all/?record={self.record.pk}")

    def _all_endpoints(self):
        return {
            "POST /documents/submit/":                self._submit,
            "GET  /documents/records/<id>/slots/":    self._slots,
            "GET  /documents/uploads/?record=":       self._uploads,
            "POST /documents/uploads/create/":        self._upload_create,
            "GET  /documents/files/?record=":         self._files,
            "GET  /documents/files/download-all/":    self._download_all,
        }

    # --- the refusals, which are the point -------------------------------

    def test_stranger_is_refused_by_every_document_endpoint(self):
        """
        The acceptance criterion, as one table. A single assertion per endpoint
        so a regression names the endpoint that broke rather than failing on
        whichever one happens to run first.
        """
        self.client.force_authenticate(self.stranger)
        for label, call in self._all_endpoints().items():
            with self.subTest(endpoint=label):
                self.assertEqual(
                    call().status_code,
                    status.HTTP_403_FORBIDDEN,
                    f"{label} served a user with no claim on the record",
                )

    def test_stranger_cannot_download_the_whole_record_as_a_zip(self):
        """
        Called out separately because it is the worst of the six: a record id in
        a query string returned every supplementary file on the record.
        """
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self._download_all().status_code, status.HTTP_403_FORBIDDEN)

    def test_stranger_cannot_write_into_someone_elses_record(self):
        """A refused upload must not leave a RecordUpload behind."""
        before = RecordUpload.objects.filter(record=self.record).count()
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self._submit().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._upload_create().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            RecordUpload.objects.filter(record=self.record).count(), before,
            "a refused request still created an upload",
        )

    def test_anonymous_is_refused_by_every_document_endpoint(self):
        for label, call in self._all_endpoints().items():
            with self.subTest(endpoint=label):
                self.assertIn(
                    call().status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                    f"{label} answered an unauthenticated caller",
                )

    # --- and the access the fix must not take away -----------------------

    def test_owner_still_reaches_every_document_endpoint(self):
        """
        The other half of the guarantee: locking strangers out is worthless if
        it locks the owner out too.
        """
        self.client.force_authenticate(self.owner)
        for label, call in self._all_endpoints().items():
            with self.subTest(endpoint=label):
                self.assertLess(
                    call().status_code, 400,
                    f"{label} refused the record's own owner",
                )

    def test_office_staff_still_reaches_every_document_endpoint(self):
        """RDCO reviews these documents; the gate is owner-or-staff, not owner-only."""
        self.client.force_authenticate(self.rdco)
        for label, call in self._all_endpoints().items():
            with self.subTest(endpoint=label):
                self.assertLess(
                    call().status_code, 400,
                    f"{label} refused office staff",
                )
