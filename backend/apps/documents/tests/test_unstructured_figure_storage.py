"""An Unstructured read stores its Figures through the existing path (IR-987).

``figures.pdf`` is read through the Unstructured adapter, replaying its
recording with one Image added (see ``test_unstructured_figures``), and the
stored Figure is served only through the permission-checked endpoint.
"""

import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ai.extraction import use_extractor
from apps.ai.extraction.shaping_unstructured import shape_unstructured
from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.ai.extraction.tests.test_unstructured_figures import caption, image, png
from apps.ai.extraction.tests.unstructured_platform_vendor import API_KEY, Vendor, recording
from apps.ai.extraction.unstructured_client import UnstructuredExtractor
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordOwner, RecordType
from apps.records.tests import make_user
from core.enums import PipelineStatus, RoleName

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


class Ungated:
    """Storage only; gating and admission are IR-850's tests."""

    leaves_campus = False

    def __init__(self, adapter):
        self._adapter = adapter
        self.timeout_seconds = adapter.timeout_seconds

    def extract(self, pdf, *, filename):
        return self._adapter.extract(pdf, filename=filename)


@pytest.fixture(autouse=True)
def no_chunking(monkeypatch):
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args, **kwargs: None)


def _record(owner):
    fixture = FIXTURES["figures"]
    record = Record.objects.create(
        title="A thesis", abstract="B" * 40, added_by=owner,
        record_type=RecordType.objects.get_or_create(name="Thesis")[0],
        pipeline_status=PipelineStatus.IN_REVIEW,
        abstract_file=SimpleUploadedFile(fixture.filename, pdf_bytes(fixture), content_type="application/pdf"),
        manuscript_revision=uuid.uuid4(),
    )
    RecordOwner.objects.create(record=record, user=owner, is_primary=True)
    extraction = PdfExtraction.objects.create(
        record=record, kind=DocumentKind.MANUSCRIPT, source_revision=record.manuscript_revision,
        source_file=record.abstract_file.name,
    )
    return record, extraction


def _read(record, data):
    elements = recording("figures")
    elements[3:3] = [image("img-1", data), caption("Figure 1: A captioned rectangle.")]
    adapter = UnstructuredExtractor(api=Vendor("figures", result=elements).api(), api_key=API_KEY,
                                    shape=shape_unstructured, sleep=lambda seconds: None)
    with use_extractor(Ungated(adapter)):
        tasks.extract_manuscript_text.apply(args=[record.id, str(record.manuscript_revision)])


def test_figures_pdf_read_through_unstructured_stores_and_serves_its_figure():
    owner = make_user("ir987-owner@cit.edu", RoleName.STUDENT)
    stranger = make_user("ir987-stranger@cit.edu", RoleName.STUDENT)
    record, extraction = _record(owner)
    data = png()

    _read(record, data)

    (figure,) = extraction.figures.all()
    assert (figure.page, figure.caption, figure.name) == (1, "Figure 1: A captioned rectangle.", "img-1")
    assert figure.bbox == pytest.approx({"x": 72.0, "y": 144.0, "w": 216.0, "h": 144.0})
    assert figure.media_type == "image/png"
    assert figure.source_revision == record.manuscript_revision
    url = reverse("record-figure", args=[record.id, figure.id])
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == data
    client.force_authenticate(stranger)
    assert client.get(url).status_code == 404
