"""IR-1203's image half: an office's file is served as what it is, and only PDF, PNG and JPEG inline.

`GET /documents/files/<id>/download/?inline=true` is how Review's reader reads
a supplementary file. It answered every file but a PDF as an
`application/octet-stream` attachment, so the reader could not show a PNG or
a JPG scan. It now serves PDF, PNG and JPEG with their own type, inline when
asked. Anything else, including an SVG (which can carry script) stored before
IR-1220 refused new ones, is still an attachment with no type a browser would
render. `SECURE_CONTENT_TYPE_NOSNIFF` keeps a browser from guessing otherwise.
"""
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.documents.models import RecordFile
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


@pytest.fixture
def stored(tmp_path, settings):
    """A record's owner, signed in, and a way to store an office's file on it."""
    settings.MEDIA_ROOT = str(tmp_path)
    owner = make_user("serving-owner@cit.edu", "Student")
    record = Record.objects.create(
        title="A paper under review", added_by=owner,
        record_type=RecordType.objects.get_or_create(name="Thesis / Research")[0],
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    client = APIClient()
    client.force_authenticate(owner)

    def store(filename, content=b"bytes"):
        return RecordFile.objects.create(
            record=record, file=ContentFile(content, name=filename), filename=filename, party="rdco",
        )
    return client, store


def read(client, record_file, inline=True):
    url = reverse("record-file-download", args=[record_file.pk])
    return client.get(url + ("?inline=true" if inline else ""))


@pytest.mark.parametrize("filename, content_type", [
    ("Signed consent.png", "image/png"),
    ("Signed consent.jpg", "image/jpeg"),
    ("Signed consent.JPEG", "image/jpeg"),
    ("Ethics clearance.pdf", "application/pdf"),
])
def test_a_pdf_png_or_jpeg_is_served_inline_as_itself(stored, filename, content_type):
    client, store = stored
    response = read(client, store(filename))
    assert response.status_code == 200
    assert response["Content-Type"] == content_type
    assert response["Content-Disposition"].startswith("inline;")
    assert response["X-Content-Type-Options"] == "nosniff"


def test_asked_for_a_download_it_is_an_attachment_of_its_own_type(stored):
    client, store = stored
    response = read(client, store("Signed consent.png"), inline=False)
    assert response["Content-Type"] == "image/png"
    assert response["Content-Disposition"].startswith("attachment;")


@pytest.mark.parametrize("filename", ["diagram.svg", "Minutes.docx", "notes.txt", "no extension"])
def test_anything_else_is_never_inline_and_never_a_type_a_browser_renders(stored, filename):
    client, store = stored
    response = read(client, store(filename, b'<svg xmlns="http://www.w3.org/2000/svg"/>'))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/octet-stream"
    assert response["Content-Disposition"].startswith("attachment;")
