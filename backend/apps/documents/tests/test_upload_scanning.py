"""
No uploaded file is stored until it has passed a malware scan (IR-666, ADR-072).

Every intake path is driven through the API with the EICAR test file, as the
test scanner (conftest.py) flags it: the upload is refused, nothing is
stored, and the refusal is audited with the file's digest and the signature,
never its bytes. A scanner that is down refuses the upload (fail closed).

The office attachment takes any type, so it is sent the EICAR file itself.
ClamAV flags EICAR only at the start of a file, so a valid PDF or image can't
carry it; those paths send one carrying `MARKER`, which the test scanner is
told to flag, to prove each asks the scan and refuses. Real ClamAV with
EICAR is CI's `malware-scan` job.
"""
import ast
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditEvent
from apps.documents.models import RecordFile, RecordUpload, UploadSlot
from apps.documents.scanning import EICAR, UNAVAILABLE, UNSAFE, FakeScanner, use_scanner

#: What the test scanner is told to flag inside a valid PDF or image.
MARKER = b"%IRIS-TEST-MALWARE"
from apps.documents.testing import pdf_upload
from apps.documents.tests import test_record_document_authorization as _authorization
from apps.records.models import Record, RecordOwner, RecordType

make_user = staticmethod(_authorization.RecordDocumentAuthorizationTests.make_user)


class _Media(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="iris-test-media-")
        cls._media = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        marked = use_scanner(FakeScanner(marker=MARKER))
        marked.__enter__()
        self.addCleanup(marked.__exit__, None, None, None)

    def refused_events(self):
        return list(AuditEvent.objects.filter(event_type=AuditEvent.UPLOAD_REFUSED_UNSAFE))


class OfficeAttachmentScanTests(_Media):
    """`POST /documents/files/upload/` takes any type, so every type is scanned."""

    make_user = make_user

    def setUp(self):
        super().setUp()
        from apps.reviews.models import RecordAssignment
        from core.enums import Party

        self.owner = self.make_user("scan-owner@cit.edu", "Student")
        self.itso = self.make_user("scan-itso@cit.edu", "ITSO")
        self.record = Record.objects.create(
            title="Under review", abstract="D" * 40, record_type=RecordType.objects.first(),
            added_by=self.owner, pipeline_status="in_review",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        RecordAssignment.objects.create(record=self.record, party=Party.ITSO)
        self.client.force_authenticate(self.itso)

    def attach(self, content, name="memo.txt"):
        return self.client.post("/api/v1/documents/files/upload/", {
            "record": self.record.pk, "file": SimpleUploadedFile(name, content),
        }, format="multipart")

    def test_the_eicar_file_is_refused_stored_nowhere_and_audited(self):
        stored_before = set(Path(self._media_root).rglob("*"))
        response = self.attach(EICAR, "eicar.com")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], UNSAFE)
        self.assertFalse(RecordFile.objects.exists())
        self.assertEqual(set(Path(self._media_root).rglob("*")), stored_before, "a refused file reached storage")

        [event] = self.refused_events()
        self.assertEqual(event.user_id, self.itso.pk)
        self.assertEqual(event.record_id, self.record.pk)
        self.assertEqual(event.metadata["where"], "office_attachment")
        self.assertEqual(event.metadata["signature"], "Eicar-Test-Signature")
        self.assertEqual(event.metadata["size"], len(EICAR))
        self.assertEqual(len(event.metadata["sha256"]), 64)
        self.assertNotIn(EICAR.decode(), str(event.metadata), "the audit kept the file's bytes")

    def test_a_clean_file_is_stored(self):
        self.assertEqual(self.attach(b"office memo").status_code, status.HTTP_201_CREATED)
        self.assertEqual(RecordFile.objects.count(), 1)
        self.assertEqual(self.refused_events(), [])

    def test_a_scanner_that_is_down_refuses_and_stores_nothing(self):
        with use_scanner(FakeScanner(down=True)):
            response = self.attach(b"office memo")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], UNAVAILABLE)
        self.assertFalse(RecordFile.objects.exists())


class SlotUploadScanTests(_Media):
    """An owner's PDF in an upload slot, new and as a new version."""

    make_user = make_user

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("slot-owner@cit.edu", "Student")
        record_type = RecordType.objects.first()
        self.record = Record.objects.create(
            title="Draft", abstract="D" * 40, record_type=record_type, added_by=self.owner, pipeline_status="draft",
        )
        RecordOwner.objects.create(record=self.record, user=self.owner, is_primary=True)
        self.slot = UploadSlot.objects.filter(record_type=record_type).first() or UploadSlot.objects.create(
            record_type=record_type, name="Ethics Clearance",
        )
        self.client.force_authenticate(self.owner)

    def test_a_flagged_pdf_is_refused_by_the_scan_and_audited(self):
        response = self.client.post("/api/v1/documents/uploads/create/", {
            "record": self.record.pk, "slot": self.slot.pk, "file": pdf_upload("form.pdf", MARKER),
        }, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data["detail"], UNSAFE)
        self.assertFalse(RecordUpload.objects.exists())
        self.assertEqual([e.metadata["where"] for e in self.refused_events()], ["upload_version"])

    def test_a_clean_pdf_is_stored(self):
        response = self.client.post("/api/v1/documents/uploads/create/", {
            "record": self.record.pk, "slot": self.slot.pk, "file": pdf_upload("form.pdf", b"clean"),
        }, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class ProfilePhotoScanTests(_Media):
    """A photo is re-encoded, but it is scanned like every upload (ADR-072)."""

    def setUp(self):
        super().setUp()
        self.user = make_user("photo-scan@cit.edu", "Student")
        self.client.force_authenticate(self.user)

    def photo(self, trailer=b""):
        from io import BytesIO

        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (400, 400), "white").save(buffer, "PNG")
        return SimpleUploadedFile("me.png", buffer.getvalue() + trailer, content_type="image/png")

    def test_a_flagged_photo_is_refused_and_nothing_stored(self):
        response = self.client.put("/api/v1/users/me/photo/", {"photo": self.photo(MARKER)}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data["detail"], UNSAFE)
        self.user.refresh_from_db()
        self.assertFalse(self.user.photo)
        self.assertEqual([e.metadata["where"] for e in self.refused_events()], ["profile_photo"])

    def test_a_clean_photo_is_stored(self):
        response = self.client.put("/api/v1/users/me/photo/", {"photo": self.photo()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class RecordImportScanTests(_Media):
    """RDCO's bulk import attaches PDFs by File Name; each is scanned."""

    def test_a_flagged_pdf_is_refused_with_its_row(self):
        from apps.records.services import check_import_pdf

        rdco = make_user("import-scan@cit.edu", "RDCO")
        pdf, problems = check_import_pdf(
            {"file_name": "paper.pdf", "row_num": 2}, {"paper.pdf": pdf_upload("paper.pdf", MARKER)}, {}, user=rdco,
        )
        self.assertIsNone(pdf)
        self.assertEqual(problems, [f'File Name "paper.pdf": {UNSAFE}'])
        self.assertEqual([e.metadata["where"] for e in self.refused_events()], ["record_import"])


class EveryIntakePathScansTests(APITestCase):
    """
    The guard ADR-072 decision 2 asks for: every module that checks an upload
    as a PDF also scans it, so a new intake path can't store a file unscanned
    by forgetting. (The office attachment, which takes any type, and the photo
    are tested above.)
    """

    def test_every_caller_of_the_pdf_check_also_scans(self):
        root = Path(__file__).resolve().parents[3]  # backend/
        unscanned = []
        for path in (root / "apps").rglob("*.py"):
            if "tests" in path.parts or path.name.startswith("test") or "migrations" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if path.name == "validators.py" or "pdf_upload_problem(" not in source:
                continue
            calls = {node.func.id for node in ast.walk(ast.parse(source))
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
            if "pdf_upload_problem" in calls and "upload_problem" not in calls:
                unscanned.append(str(path.relative_to(root)))
        self.assertEqual(unscanned, [], "these check uploads as PDFs but never scan them (ADR-072)")
