"""A vendor's raw result and credits are stored on the extraction (IR-841)."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai.chunking.document import PARAGRAPH, DocumentElement, NormalizedDocument
from apps.ai.extraction import ExtractedDocument, Provenance, Usage, use_extractor
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]

RAW = {
    "job": {"id": "pjb-1", "status": "COMPLETED", "usage": {"credits": 33.0}},
    "metadata": {"pages": [{"page_number": 1, "confidence": 0.3, "printed_page_number": "iv"}]},
    "grounded_items": [{"page_number": 1, "items": []}],
}


class RawExtractor:
    timeout_seconds = 60
    # Storage only; gating and admission are IR-850's tests.
    leaves_campus = False

    def extract(self, pdf_bytes, *, filename):
        return ExtractedDocument(
            document=NormalizedDocument(
                title="", elements=(DocumentElement(kind=PARAGRAPH, text="A passage.", page=1),),
                page_sizes={1: (612.0, 792.0)},
            ),
            provenance=Provenance(name="llamaparse", version="2026-09-28", options={"tier": "agentic"}),
            usage=Usage(pages=1, credits=Decimal("33.0")),
            raw=RAW,
        )


@pytest.fixture(autouse=True)
def no_chunking(monkeypatch):
    monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args, **kwargs: None)


def test_the_raw_result_and_credits_are_stored_with_their_provenance():
    record = Record.objects.create(
        title="A thesis", record_type=RecordType.objects.create(name="Thesis"),
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
    )
    extraction = PdfExtraction.objects.create(record=record, kind=DocumentKind.MANUSCRIPT)

    with use_extractor(RawExtractor()):
        tasks.extract_manuscript_text.apply(args=[record.id])

    extraction.refresh_from_db()
    assert extraction.status == "done"
    assert extraction.raw_result == RAW
    assert extraction.credits == Decimal("33.0")
    assert extraction.pages_read == 1
    assert (extraction.extractor, extraction.extractor_version) == ("llamaparse", "2026-09-28")
    assert extraction.extractor_options == {"tier": "agentic"}
