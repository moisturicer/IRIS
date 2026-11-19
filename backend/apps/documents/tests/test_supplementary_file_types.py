"""IR-1220: an office's supplementary file is PDF, Word (.docx), PNG or JPG, by name and by bytes.

`POST /documents/files/upload/` (`attach_file`, ADR-032 §10 as amended
2026-11-18) was the one upload in IRIS that took any type. It now takes the
types every other upload already keeps to, and checks the file's first bytes
as well as its name, so a renamed file is refused. Nothing refused is stored.
"""
import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.documents.models import RecordFile
from apps.documents.testing import real_pdf_bytes
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

REFUSED = "Only PDF, Word, PNG or JPG files are accepted."

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 32
# Word 97-2003 (.doc), Excel's .xls, PowerPoint's .ppt and a Windows installer
# (.msi) are all OLE2 compound files, which begin with this one header. So the
# first bytes cannot tell a .doc from an installer, and .doc is not accepted.
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 56


def zip_bytes(names: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in names.items():
            archive.writestr(name, content)
    return buffer.getvalue()


DOCX = zip_bytes({
    "[Content_Types].xml": b'<?xml version="1.0"?><Types/>',
    "word/document.xml": b'<?xml version="1.0"?><w:document/>',
})
ZIP = zip_bytes({"notes.txt": b"office notes"})
# A macro-carrying document saved as .docx: Word keeps macros in vbaProject.bin.
DOCX_WITH_MACROS = zip_bytes({
    "[Content_Types].xml": b'<?xml version="1.0"?><Types/>',
    "word/document.xml": b'<?xml version="1.0"?><w:document/>',
    "word/vbaProject.bin": b"\xd0\xcf\x11\xe0",
})


@pytest.fixture
def office(tmp_path, settings):
    """RDCO taking part in a record's review, seated and signed in: who may attach (IR-474, IR-1226)."""
    from apps.reviews.models import RecordAssignment, ReviewerSeat

    settings.MEDIA_ROOT = str(tmp_path)
    owner = make_user("types-owner@cit.edu", "Student")
    record = Record.objects.create(
        title="A paper under review", added_by=owner,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    member = make_user("types-office@cit.edu", "RDCO")
    # Filing takes a seat on the assignment, not membership of the office (IR-1226).
    ReviewerSeat.objects.create(assignment=RecordAssignment.objects.create(record=record, party="rdco"), reviewer=member)
    client = APIClient()
    client.force_authenticate(member)
    return client, record


def attach(client, record, name, content, content_type="application/octet-stream"):
    return client.post(reverse("record-file-upload"), {
        "record": record.pk, "file": SimpleUploadedFile(name, content, content_type=content_type),
    }, format="multipart")


@pytest.mark.parametrize("name, content", [
    ("Survey results.docx", DOCX),
    ("Signed consent.png", PNG),
    ("Signed consent.jpg", JPG),
    ("Signed consent.JPEG", JPG),
])
def test_docx_png_and_jpg_are_accepted(office, name, content):
    client, record = office
    response = attach(client, record, name, content)
    assert response.status_code == 201, response.data
    assert RecordFile.objects.get(record=record).filename == name


def test_a_pdf_is_accepted_after_its_safety_check(office):
    """The PDF safety check runs only on Linux, so on Windows this one answers 'temporarily unavailable'."""
    client, record = office
    response = attach(client, record, "Ethics clearance.pdf", real_pdf_bytes(), "application/pdf")
    assert response.status_code == 201, response.data


@pytest.mark.parametrize("name, content", [
    ("diagram.svg", SVG),
    ("setup.exe", EXE),
    ("all files.zip", ZIP),
    ("notes.txt", b"office notes"),
    ("no extension", PNG),
    # Word 97-2003 is re-saved as .docx (ADR-032 §10 as amended 2026-11-18).
    ("Survey results.doc", OLE2),
    ("installer.msi", OLE2),
    # Renamed: the bytes are not what the name says.
    ("scan.pdf", PNG),
    ("scan.png", real_pdf_bytes()),
    ("diagram.png", SVG),
    ("archive.docx", ZIP),
    ("archive.doc", ZIP),
    ("setup.docx", OLE2),
    ("photo.jpg", PNG),
    ("macros.docx", DOCX_WITH_MACROS),
])
def test_any_other_type_or_a_renamed_file_is_refused_and_nothing_is_stored(office, name, content):
    client, record = office
    response = attach(client, record, name, content)
    assert response.status_code == 400, response.data
    assert response.data["detail"] == REFUSED
    assert response.data["file"] == [REFUSED]
    assert not RecordFile.objects.filter(record=record).exists()


def test_an_empty_file_is_refused(office):
    client, record = office
    response = attach(client, record, "empty.png", b"")
    assert response.status_code == 400
    assert not RecordFile.objects.filter(record=record).exists()
