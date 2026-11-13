"""The PDF evidence is read at extraction and stored beside the raw result (IR-1053)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import ExtractedDocument, Provenance, use_extractor
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction, RecordUpload, UploadSlot
from apps.documents.pdf_evidence import sandbox
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

EVIDENCE = {"reader": sandbox.READER, "error": "", "page_count": 1,
            "pages": [{"page": 1, "width": 612.0, "height": 792.0, "has_text_layer": False}],
            "bookmarks": [], "page_labels": ["i"], "contents": []}


class Extractor:
    timeout_seconds = 60
    leaves_campus = False

    def extract(self, pdf_bytes, *, filename):
        return ExtractedDocument(
            document=NormalizedDocument(
                title="", elements=(DocumentElement(kind=PARAGRAPH, text="A passage.", page=1),),
                page_sizes={1: (612.0, 792.0)},
            ),
            provenance=Provenance(name="llamaparse", version="2026-09-28", options={}),
            raw={"job": {"id": "pjb-1"}},
        )


@pytest.fixture(autouse=True)
def no_chunking(monkeypatch):
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args, **kwargs: None)


@pytest.fixture
def read(monkeypatch):
    seen = []

    def fake(pdf_bytes):
        seen.append(pdf_bytes)
        return EVIDENCE

    monkeypatch.setattr(sandbox, "read_pdf_evidence", fake)
    return seen


def manuscript(data=b"%PDF-1.7 thesis bytes"):
    record = Record.objects.create(
        title="A thesis", record_type=RecordType.objects.create(name="Thesis"),
        abstract_file=SimpleUploadedFile("thesis.pdf", data),
    )
    PdfExtraction.objects.create(record=record, kind=DocumentKind.MANUSCRIPT)
    return record


def test_a_manuscript_stores_the_evidence_of_its_own_bytes(read):
    record = manuscript()

    with use_extractor(Extractor()):
        tasks.extract_manuscript_text.apply(args=[record.id])

    extraction = PdfExtraction.objects.get(record=record)
    assert extraction.status == "done"
    assert extraction.pdf_evidence == EVIDENCE
    assert extraction.raw_result == {"job": {"id": "pjb-1"}}
    assert read == [b"%PDF-1.7 thesis bytes"]


def test_a_malformed_pdf_still_completes_and_records_the_error():
    # The real runner: on Linux the child reports it unreadable; elsewhere the
    # sandbox is unsupported. Either way the error is stored and nothing fails.
    record = manuscript(b"%PDF-1.7 not really a pdf")

    with use_extractor(Extractor()):
        tasks.extract_manuscript_text.apply(args=[record.id])

    extraction = PdfExtraction.objects.get(record=record)
    assert extraction.status == "done"
    assert extraction.pdf_evidence["error"] in {"unreadable", "sandbox_unsupported"}
    assert extraction.pdf_evidence["pages"] == []


def test_a_supplementary_upload_is_not_read(read):
    record = Record.objects.create(title="A thesis", record_type=RecordType.objects.create(name="Thesis"))
    slot = UploadSlot.objects.create(record_type=record.record_type, name="Appendix")
    upload = RecordUpload.objects.create(
        record=record, slot=slot, file=SimpleUploadedFile("appendix.pdf", b"%PDF-1.7 appendix"))
    PdfExtraction.objects.create(upload=upload, kind=DocumentKind.SUPPLEMENTARY)

    with use_extractor(Extractor()):
        tasks.extract_pdf_text.apply(args=[upload.id])

    extraction = PdfExtraction.objects.get(upload=upload)
    assert extraction.status == "done"
    assert extraction.pdf_evidence == {}
    assert read == []
