"""The RAG corpus boundary is a stored document kind, not a code path (IR-239).

IR-195 got the *behaviour* right and the *mechanism* wrong: it decided whether
to chunk by which Celery task happened to run, which is decided in turn by
which endpoint received the file. [ADR-013](docs/adr/013-chunk-level-rag-pipeline.md)
§Decision ("Retrieval scope") asks for the opposite in as many words -- the
chunker must key off "is this the manuscript," *not* off the upload path.

That distinction is invisible while the two coincide, so the test that carries
this ticket is ``test_a_manuscript_arriving_through_the_upload_path_is_chunked``
below: a row marked MANUSCRIPT but attached to an ``UploadSlot``. Under IR-195
that case was unreachable *and* unhandled; here it is unreachable and handled,
which is the whole difference.

Needs a database because ``PdfExtraction`` is the thing under test.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.ai.extraction import ExtractedDocument
from apps.ai.chunking.document import HEADING, PARAGRAPH, DocumentElement, NormalizedDocument
from apps.documents import tasks
from apps.documents.models import DocumentKind, PdfExtraction, RecordUpload, UploadSlot
from apps.records.models import Record, RecordType

pytestmark = [pytest.mark.db_required, pytest.mark.django_db]


DOCUMENT = NormalizedDocument(
    title="Optimization of Tilapia Feed Conversion",
    elements=(
        DocumentElement(kind=HEADING, text="3 Methodology", level=2, page=12),
        DocumentElement(kind=PARAGRAPH, text="Samples were collected weekly.", page=12),
    ),
    page_sizes={12: (612.0, 792.0)},
)


class FakeExtractor:
    """Returns a canned document. A real implementation of the port."""

    def extract(self, pdf_bytes, *, filename):
        return ExtractedDocument(document=DOCUMENT, extractor="fake")


@pytest.fixture(autouse=True)
def queued_chunkings(monkeypatch):
    """Every extraction id handed to the chunking task, in place of a real
    ``delay``. Autouse, because a test that forgot it would block on a broker
    rather than fail."""
    calls = []
    monkeypatch.setattr(
        tasks, "_queue_chunk_extraction", lambda extraction_id: calls.append(extraction_id)
    )
    return calls


@pytest.fixture(autouse=True)
def fake_extractor(monkeypatch):
    monkeypatch.setattr(tasks, "_build_extractor", lambda: FakeExtractor())


@pytest.fixture
def record(db):
    record_type = RecordType.objects.create(name="Thesis")
    return Record.objects.create(
        title="A thesis",
        record_type=record_type,
        abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake bytes"),
    )


@pytest.fixture
def upload(record):
    slot = UploadSlot.objects.create(name="Ethics Clearance", record_type=record.record_type)
    return RecordUpload.objects.create(
        record=record,
        slot=slot,
        file=SimpleUploadedFile("clearance.pdf", b"%PDF-1.7 fake bytes"),
    )


# ---------------------------------------------------------------------------
# The marker itself
# ---------------------------------------------------------------------------


def test_an_unmarked_extraction_defaults_to_supplementary(upload):
    """Fails closed. A row whose creator said nothing must stay out of the
    corpus rather than be indexed into it by default."""
    extraction = PdfExtraction.objects.create(upload=upload)

    assert extraction.kind == DocumentKind.SUPPLEMENTARY


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


def test_a_supplementary_extraction_is_not_chunked(upload, queued_chunkings):
    PdfExtraction.objects.create(upload=upload, kind=DocumentKind.SUPPLEMENTARY)

    tasks.extract_pdf_text.apply(args=[upload.id])

    assert queued_chunkings == []


def test_a_manuscript_extraction_is_chunked(record, queued_chunkings):
    extraction = PdfExtraction.objects.create(record=record, kind=DocumentKind.MANUSCRIPT)

    tasks.extract_manuscript_text.apply(args=[record.id])

    assert queued_chunkings == [extraction.id]


def test_a_manuscript_arriving_through_the_upload_path_is_chunked(upload, queued_chunkings):
    """The case IR-239 exists for.

    A manuscript attached to an UploadSlot has no path to reach it today, and
    under IR-195 it would have been silently excluded -- `extract_pdf_text`
    queued nothing, because of what task it was rather than what it held.
    Keyed on `kind`, the same row is chunked.
    """
    extraction = PdfExtraction.objects.create(upload=upload, kind=DocumentKind.MANUSCRIPT)

    tasks.extract_pdf_text.apply(args=[upload.id])

    assert queued_chunkings == [extraction.id]


def test_a_supplementary_record_keyed_extraction_is_not_chunked(record, queued_chunkings):
    """The mirror of the case above, and the reason `kind` is stored rather
    than derived from `record_id is not None` -- deriving it would make this
    row chunk on the strength of which column is populated."""
    PdfExtraction.objects.create(record=record, kind=DocumentKind.SUPPLEMENTARY)

    tasks.extract_manuscript_text.apply(args=[record.id])

    assert queued_chunkings == []


def test_the_submit_endpoint_marks_what_it_writes(record, upload, tmp_path, settings):
    """The supplementary half of "both paths set it explicitly".

    Asserted through the endpoint rather than by reading ``views.py``,
    because what matters is the row that reaches the database -- the default
    would make a forgotten ``kind`` look identical from the outside.
    """
    from unittest import mock

    from django.core.files.uploadedfile import SimpleUploadedFile
    from rest_framework.test import APIClient

    from apps.accounts.models import Role, User
    from apps.records.models import RecordOwner

    settings.MEDIA_ROOT = str(tmp_path)
    user = User.objects.create_user(
        email="submitter@cit.edu", password="pw12345!",
        first_name="Test", last_name="User",
        role=Role.objects.get_or_create(name="Student")[0], is_verified=True,
    )
    # Owner, not a stranger -- the documents endpoints are ownership-gated
    # (IR-153/IR-120), and this test is about `kind`, not authorization.
    RecordOwner.objects.create(record=record, user=user, is_primary=True)
    client = APIClient()
    client.force_authenticate(user)

    with mock.patch("apps.documents.tasks.extract_pdf_text.delay"):
        response = client.post(
            "/api/v1/documents/submit/",
            {
                "record": record.pk,
                "slot": upload.slot.pk,
                "file": SimpleUploadedFile(
                    "clearance.pdf", b"%PDF-1.4 x", content_type="application/pdf"
                ),
            },
            format="multipart",
        )

    assert response.status_code == 201, response.data
    written = PdfExtraction.objects.get(pk=response.data["extraction"]["id"])
    assert written.kind == DocumentKind.SUPPLEMENTARY


def test_a_failed_extraction_is_not_chunked_whatever_its_kind(record, queued_chunkings, monkeypatch):
    """Kind decides *whether* a good extraction belongs in the corpus, not
    whether a broken one does."""

    class FailingExtractor:
        def extract(self, pdf_bytes, *, filename):
            raise RuntimeError("Docling-serve unreachable")

    monkeypatch.setattr(tasks, "_build_extractor", lambda: FailingExtractor())
    PdfExtraction.objects.create(record=record, kind=DocumentKind.MANUSCRIPT)

    tasks.extract_manuscript_text.apply(args=[record.id])

    assert queued_chunkings == []
