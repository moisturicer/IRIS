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


class RecordFileUploadAuthorizationTests(APITestCase):
    """
    IR-474: `POST /documents/files/upload/` -- an office filing a supplementary
    file of its own (`attach_file`, ADR-032 §10 as amended 2026-10-06).

    The route checked only `IsStaff`, then wrote a `RecordFile` onto whatever
    record id the body named. `authorize_record_documents` alone would not close
    that: `owns_or_staffs_record` admits every office, so any KTTO, RDCO, ITSO or
    IERC account would still pass. ADR-032 grants `attach_file` on a record the
    office *takes part in*, so the gate is participation -- an active assignment
    the user can staff, the same test that offers the action in Paper View.

    The refusals follow ADR-022 §Amendment 4. Office staff can see every
    record, so an office that does not take part is refused with a **403**, not
    a 404 that would pretend a visible record is missing. A record id that
    names nothing is a 404.

    This route is not in `RecordDocumentAuthorizationTests._all_endpoints()`:
    that matrix admits the owner and any office, and this route admits neither
    by that rule alone. Its own matrix is here.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    make_user = staticmethod(RecordDocumentAuthorizationTests.make_user)

    def setUp(self):
        from apps.reviews.models import RecordAssignment
        from core.enums import Party

        self.owner    = self.make_user("attach-owner@cit.edu", "Student")
        self.stranger = self.make_user("attach-stranger@cit.edu", "Student")
        self.itso     = self.make_user("attach-itso@cit.edu", "ITSO")
        self.ktto     = self.make_user("attach-ktto@cit.edu", "KTTO")

        record_type = RecordType.objects.first()
        self.assertIsNotNone(record_type, "no seeded RecordType -- migrations incomplete")
        self.record = Record.objects.create(
            title="Disclosure Under Review", abstract="D" * 40,
            record_type=record_type, added_by=self.owner,
            pipeline_status="itso_review",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        # ITSO holds the record; KTTO has no part in it.
        RecordAssignment.objects.create(record=self.record, party=Party.ITSO)

    def _attach(self, record_id=None):
        return self.client.post(
            "/api/v1/documents/files/upload/",
            {
                "record": self.record.pk if record_id is None else record_id,
                "file": SimpleUploadedFile("memo.txt", b"office memo"),
            },
            format="multipart",
        )

    def _files_on_record(self):
        return RecordFile.objects.filter(record=self.record).count()

    def test_an_office_taking_part_can_attach(self):
        self.client.force_authenticate(self.itso)
        response = self._attach()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(self._files_on_record(), 1)

    def test_an_office_with_no_part_is_refused_and_nothing_is_written(self):
        self.client.force_authenticate(self.ktto)
        self.assertEqual(self._attach().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._files_on_record(), 0, "a refused attach still created a RecordFile")

    def test_an_office_whose_assignment_completed_is_refused(self):
        """Taking part is present tense: a completed assignment grants nothing."""
        from core.enums import AssignmentState

        self.record.assignments.update(state=AssignmentState.COMPLETED)
        self.client.force_authenticate(self.itso)
        self.assertEqual(self._attach().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._files_on_record(), 0)

    def test_a_record_that_does_not_exist_is_a_404(self):
        self.client.force_authenticate(self.itso)
        missing = Record.objects.order_by("-pk").first().pk + 1000
        for record_id in (missing, "not-an-id"):
            with self.subTest(record=record_id):
                self.assertEqual(
                    self._attach(record_id).status_code, status.HTTP_404_NOT_FOUND,
                )
        self.assertFalse(RecordFile.objects.exists())

    def test_a_student_is_refused_by_role_even_on_their_own_record(self):
        """Owners file through the slot upload, not here (no change)."""
        for user in (self.owner, self.stranger):
            with self.subTest(user=user.email):
                self.client.force_authenticate(user)
                self.assertEqual(self._attach().status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._files_on_record(), 0)

    def test_anonymous_is_refused(self):
        self.assertIn(
            self._attach().status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertEqual(self._files_on_record(), 0)


class RecordFileRemovalAuthorizationTests(APITestCase):
    """
    IR-476: `DELETE /documents/files/<id>/` -- the removal half of `attach_file`
    (ADR-032 §10 as amended 2026-10-06: an office files a supplementary file of
    its own on a record it takes part in, "and may remove one").

    The route authorized with `owns_or_staffs_record`, which admits every
    office, so any KTTO, RDCO, ITSO or IERC account could delete any office's
    file on any record -- from disk, so it could not be undone. A file now
    belongs to the office that filed it (`RecordFile.party`), and removing it
    takes the same office while it holds an active assignment on the record:
    the attach rule (IR-474), plus ownership of the file.

    Owners lose the delete `owns_or_staffs_record` gave them; the screen never
    offered it. Refusals follow ADR-022 §Amendment 4: a missing file, or one on
    a record the caller cannot see, is a 404; a file the caller can see but may
    not remove is a 403.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    make_user = staticmethod(RecordDocumentAuthorizationTests.make_user)

    def setUp(self):
        from apps.reviews.models import RecordAssignment
        from core.enums import Party

        self.owner    = self.make_user("remove-owner@cit.edu", "Student")
        self.stranger = self.make_user("remove-stranger@cit.edu", "Student")
        self.itso     = self.make_user("remove-itso@cit.edu", "ITSO")
        self.ierc     = self.make_user("remove-ierc@cit.edu", "IERC")
        self.ktto     = self.make_user("remove-ktto@cit.edu", "KTTO")
        self.rdco     = self.make_user("remove-rdco@cit.edu", "RDCO")

        self.record_type = RecordType.objects.first()
        self.assertIsNotNone(self.record_type, "no seeded RecordType -- migrations incomplete")
        self.record = self._record("parallel_review")
        # ITSO and IERC both hold the record; KTTO has no part in it.
        RecordAssignment.objects.create(record=self.record, party=Party.ITSO)
        RecordAssignment.objects.create(record=self.record, party=Party.IERC)

        self.itso_file = self._file(self.record, "itso", self.itso)
        self.ierc_file = self._file(self.record, "ierc", self.ierc)

    def _record(self, pipeline_status):
        record = Record.objects.create(
            title=f"Disclosure at {pipeline_status}", abstract="D" * 40,
            record_type=self.record_type, added_by=self.owner,
            pipeline_status=pipeline_status,
        )
        RecordOwner.objects.create(record=record, user=self.owner, is_primary=True)
        return record

    @staticmethod
    def _file(record, party, uploaded_by):
        from django.core.files.base import ContentFile

        return RecordFile.objects.create(
            record=record, file=ContentFile(b"office memo", name=f"{party}-memo.txt"),
            filename=f"{party}-memo.txt", uploaded_by=uploaded_by, party=party,
        )

    def _remove(self, record_file):
        pk = record_file if isinstance(record_file, int) else record_file.pk
        return self.client.delete(f"/api/v1/documents/files/{pk}/")

    def assertRemoved(self, record_file, response):
        from django.core.files.storage import default_storage

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, getattr(response, "data", None))
        self.assertFalse(RecordFile.objects.filter(pk=record_file.pk).exists())
        self.assertFalse(default_storage.exists(record_file.file.name), "the stored file was left behind")

    def assertSurvives(self, record_file, response, code=status.HTTP_403_FORBIDDEN):
        from django.core.files.storage import default_storage

        self.assertEqual(response.status_code, code, getattr(response, "data", None))
        self.assertTrue(RecordFile.objects.filter(pk=record_file.pk).exists(), "a refused remove deleted the row")
        self.assertTrue(default_storage.exists(record_file.file.name), "a refused remove deleted the stored file")

    # --- who may remove -------------------------------------------------------

    def test_an_office_taking_part_can_remove_its_own_file(self):
        self.client.force_authenticate(self.itso)
        self.assertRemoved(self.itso_file, self._remove(self.itso_file))

    def test_an_office_cannot_remove_another_offices_file(self):
        self.client.force_authenticate(self.itso)
        self.assertSurvives(self.ierc_file, self._remove(self.ierc_file))

    def test_an_office_with_no_part_cannot_remove_anything(self):
        self.client.force_authenticate(self.ktto)
        for record_file in (self.itso_file, self.ierc_file):
            with self.subTest(file=record_file.filename):
                self.assertSurvives(record_file, self._remove(record_file))

    def test_an_office_whose_assignment_is_not_active_cannot_remove_its_own_file(self):
        """Taking part is present tense: a completed assignment grants nothing."""
        from core.enums import AssignmentState, Party

        self.record.assignments.filter(party=Party.ITSO).update(state=AssignmentState.COMPLETED)
        self.client.force_authenticate(self.itso)
        self.assertSurvives(self.itso_file, self._remove(self.itso_file))

    def test_an_owner_cannot_remove_an_office_attachment_on_their_own_record(self):
        self.client.force_authenticate(self.owner)
        self.assertSurvives(self.itso_file, self._remove(self.itso_file))

    def test_a_file_no_office_owns_is_removable_by_no_one(self):
        """A backfilled row with no party is left to the admin escape hatch."""
        orphan = self._file(self.record, "orphan", None)
        RecordFile.objects.filter(pk=orphan.pk).update(party=None)
        for user in (self.itso, self.ierc, self.rdco, self.owner):
            with self.subTest(user=user.email):
                self.client.force_authenticate(user)
                self.assertSurvives(orphan, self._remove(orphan))

    def test_rdco_can_remove_its_own_file_at_either_rdco_stage(self):
        from apps.reviews.models import RecordAssignment
        from core.enums import Party

        for pipeline_status, party in (("rdco_intake", Party.INTAKE), ("rdco_review", Party.RDCO)):
            with self.subTest(stage=pipeline_status):
                record = self._record(pipeline_status)
                RecordAssignment.objects.create(record=record, party=party)
                record_file = self._file(record, "rdco", self.rdco)
                self.client.force_authenticate(self.rdco)
                self.assertRemoved(record_file, self._remove(record_file))

    # --- refusals ------------------------------------------------------------

    def test_a_file_that_does_not_exist_is_a_404(self):
        self.client.force_authenticate(self.itso)
        missing = RecordFile.objects.order_by("-pk").first().pk + 1000
        self.assertEqual(self._remove(missing).status_code, status.HTTP_404_NOT_FOUND)

    def test_a_file_on_a_record_the_caller_cannot_see_is_a_404(self):
        """ADR-022 §Amendment 4: an unseen Record reads as a missing id."""
        self.client.force_authenticate(self.stranger)
        self.assertSurvives(self.itso_file, self._remove(self.itso_file), status.HTTP_404_NOT_FOUND)

    def test_anonymous_is_refused(self):
        response = self._remove(self.itso_file)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertTrue(RecordFile.objects.filter(pk=self.itso_file.pk).exists())

    # --- what attaching stores ----------------------------------------------

    def _attach(self, record):
        return self.client.post(
            "/api/v1/documents/files/upload/",
            {"record": record.pk, "file": SimpleUploadedFile("memo.txt", b"office memo")},
            format="multipart",
        )

    def test_attaching_stores_the_uploaders_party(self):
        self.client.force_authenticate(self.ierc)
        response = self._attach(self.record)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(RecordFile.objects.get(pk=response.data["id"]).party, "ierc")
        self.assertTrue(response.data["can_remove"])

    def test_rdco_attaching_at_intake_stores_rdco_never_intake(self):
        from apps.reviews.models import RecordAssignment
        from core.enums import Party

        record = self._record("rdco_intake")
        RecordAssignment.objects.create(record=record, party=Party.INTAKE)
        self.client.force_authenticate(self.rdco)
        response = self._attach(record)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(RecordFile.objects.get(pk=response.data["id"]).party, "rdco")
        self.assertTrue(response.data["can_remove"], "RDCO could not remove what it just filed at intake")

    # --- the screen follows the server ---------------------------------------

    @staticmethod
    def _can_remove_by_id(files):
        return {f["id"]: f["can_remove"] for f in files}

    def test_the_file_list_carries_can_remove_per_file(self):
        expected = {
            self.itso:  {self.itso_file.pk: True,  self.ierc_file.pk: False},
            self.ierc:  {self.itso_file.pk: False, self.ierc_file.pk: True},
            self.ktto:  {self.itso_file.pk: False, self.ierc_file.pk: False},
            self.owner: {self.itso_file.pk: False, self.ierc_file.pk: False},
        }
        for user, can_remove in expected.items():
            with self.subTest(user=user.email):
                self.client.force_authenticate(user)
                response = self.client.get("/api/v1/documents/files/", {"record": self.record.pk})
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                data = response.data
                results = data["results"] if isinstance(data, dict) else data
                self.assertEqual(self._can_remove_by_id(results), can_remove)

    def test_the_record_detail_payload_carries_can_remove_per_file(self):
        expected = {
            self.itso:  {self.itso_file.pk: True,  self.ierc_file.pk: False},
            self.owner: {self.itso_file.pk: False, self.ierc_file.pk: False},
        }
        for user, can_remove in expected.items():
            with self.subTest(user=user.email):
                self.client.force_authenticate(user)
                response = self.client.get(f"/api/v1/records/{self.record.pk}/")
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(self._can_remove_by_id(response.data["files"]), can_remove)


class RecordFileAdminTests(APITestCase):
    """
    IR-476 decision 5: the escape hatch. A file no office may remove -- one
    with no party, or one whose office no longer takes part -- is removed by
    the superuser in Django admin, which logs it, and the stored file goes too.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        from django.core.files.base import ContentFile

        owner = RecordDocumentAuthorizationTests.make_user("admin-owner@cit.edu", "Student")
        record = Record.objects.create(
            title="Disclosure With An Orphan File", abstract="D" * 40,
            record_type=RecordType.objects.first(), added_by=owner,
        )
        self.record_file = RecordFile.objects.create(
            record=record, file=ContentFile(b"office memo", name="orphan.txt"),
            filename="orphan.txt", uploaded_by=None, party=None,
        )
        self.superuser = User.objects.create_superuser(
            email="admin-root@cit.edu", password="TestPass123!",
            first_name="Root", last_name="User", is_verified=True,
        )

    def _delete_url(self):
        return f"/admin/documents/recordfile/{self.record_file.pk}/delete/"

    def test_the_superuser_deleting_a_file_in_admin_removes_the_stored_file(self):
        from django.contrib.admin.models import DELETION, LogEntry
        from django.core.files.storage import default_storage

        name = self.record_file.file.name
        self.client.force_login(self.superuser)
        response = self.client.post(self._delete_url(), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RecordFile.objects.filter(pk=self.record_file.pk).exists())
        self.assertFalse(default_storage.exists(name), "admin delete left the stored file behind")
        self.assertTrue(LogEntry.objects.filter(action_flag=DELETION, user=self.superuser).exists())

    def test_the_admin_bulk_delete_removes_the_stored_files(self):
        from django.core.files.storage import default_storage

        name = self.record_file.file.name
        self.client.force_login(self.superuser)
        response = self.client.post(
            "/admin/documents/recordfile/",
            {"action": "delete_selected", "_selected_action": [self.record_file.pk], "post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RecordFile.objects.filter(pk=self.record_file.pk).exists())
        self.assertFalse(default_storage.exists(name), "bulk delete left the stored file behind")

    def test_an_office_admin_account_is_not_the_escape_hatch(self):
        """Only the superuser: a Django `is_staff` office account is refused."""
        rdco = RecordDocumentAuthorizationTests.make_user("admin-rdco@cit.edu", "RDCO")
        User.objects.filter(pk=rdco.pk).update(is_staff=True)
        rdco.refresh_from_db()
        self.client.force_login(rdco)
        self.client.post(self._delete_url(), {"post": "yes"})
        self.assertTrue(RecordFile.objects.filter(pk=self.record_file.pk).exists())
