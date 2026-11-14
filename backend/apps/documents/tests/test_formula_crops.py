"""Each hi_res Formula is cropped from the stored PDF at 300 dpi (IR-1102).

The Extractor's OCR text is never kept as the formula: shaping leaves a
Formula as a crop with no text, and its box is rendered from the PDF.
"""

import base64
import io
import json
import sys
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.ai.chunking.document import BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.extraction import InMemoryExtractor, use_extractor
from apps.ai.extraction.shaping_unstructured import shape_unstructured
from apps.ai.extraction.tests.fixtures import FIXTURES, pdf_bytes
from apps.documents import formulas, tasks
from apps.documents.pdf_evidence import crops

LAYOUT = {"layout_width": 2125, "layout_height": 2750, "system": "PixelSpace"}
OCR = "N-1 |A) = >> 2(n)|n). n=0"


def formula_item(element_id="eq-1", page=1):
    points = [[250, 500], [250, 600], [1000, 600], [1000, 500]]
    return {"type": "Formula", "element_id": element_id, "text": OCR,
            "metadata": {"page_number": page, "coordinates": {"points": points, **LAYOUT}}}


def shaped(*items):
    return shape_unstructured({"elements": list(items)})


def formula_document():
    element = DocumentElement(
        kind="image", text="", page=1, source_label="Formula", figure="eq-1",
        bboxes=(BoundingBox(page=1, left=72.0, top=144.0, right=288.0, bottom=180.0),),
    )
    return NormalizedDocument(title="", elements=(element,), page_sizes={1: (612.0, 792.0)})


def png_size(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def test_shaping_keeps_a_formula_as_a_crop_without_its_ocr_text():
    (element,) = shaped(formula_item()).elements

    assert (element.kind, element.text, element.figure) == ("image", "", "eq-1")


def test_each_formula_is_a_target_with_its_page_and_box_in_points():
    (target,) = formulas.targets(shaped(formula_item()))

    assert (target.name, target.page) == ("eq-1", 1)
    assert target.bbox == pytest.approx({"x": 72.0, "y": 144.0, "w": 216.0, "h": 28.8})


def test_an_image_or_a_boxless_formula_is_not_a_target():
    document = shaped(
        {"type": "Image", "element_id": "img", "text": "", "metadata": {
            "page_number": 1, "coordinates": {"points": [[0, 0], [0, 9], [9, 9], [9, 0]], **LAYOUT}}},
        {"type": "Formula", "element_id": "eq-2", "text": OCR, "metadata": {"page_number": 1}},
    )

    assert formulas.targets(document) == []


def test_a_box_is_rendered_from_the_pdf_at_300_dpi():
    target = formulas.targets(formula_document())[0]

    (data,) = crops.render(pdf_bytes(FIXTURES["figures"]), [target.fractions((612.0, 792.0))], max_pages=50)

    assert data.startswith(formulas.PNG)
    scale = crops.DPI / 72
    width, height = png_size(data)
    assert width == pytest.approx((216 + 2 * crops.PAD) * scale, abs=2)
    assert height == pytest.approx((36 + 2 * crops.PAD) * scale, abs=2)


def test_a_box_off_the_document_is_none_and_the_rest_still_render():
    boxes = [{"page": 99, "box": [0.1, 0.1, 0.2, 0.2]}, {"page": 1, "box": [0.1, 0.1, 0.2, 0.2]}]

    missing, rendered = crops.render(pdf_bytes(FIXTURES["figures"]), boxes, max_pages=50)

    assert missing is None and rendered.startswith(formulas.PNG)


def test_the_sandbox_output_is_read_only_as_one_png_per_box():
    png = base64.b64encode(formulas.PNG + b"rest").decode()
    not_png = base64.b64encode(b"GIF89a").decode()

    assert formulas._read(json.dumps({"crops": [png, None, not_png]}), 3) == [formulas.PNG + b"rest", None, None]
    assert formulas._read(json.dumps({"crops": [png]}), 2) == []
    assert formulas._read("not json", 1) == []


@pytest.mark.skipif(sys.platform != "linux", reason="the crop sandbox needs Linux rlimits")
def test_crop_renders_each_target_in_the_sandbox():
    ((target, data),) = formulas.crop(pdf_bytes(FIXTURES["figures"]), formula_document())

    assert target.name == "eq-1" and data.startswith(formulas.PNG)


@pytest.mark.skipif(sys.platform == "linux", reason="checks the non-Linux refusal")
def test_off_linux_nothing_is_cropped():
    assert formulas.crop(pdf_bytes(FIXTURES["figures"]), formula_document()) == []


@pytest.mark.db_required
@pytest.mark.django_db
class ExtractionStoresCropsTests:
    @pytest.fixture
    def extraction(self):
        from apps.documents.models import DocumentKind, PdfExtraction
        from apps.records.models import Record, RecordType

        revision = uuid.uuid4()
        record = Record.objects.create(
            title="A thesis", record_type=RecordType.objects.create(name="Thesis"),
            abstract_file=SimpleUploadedFile("thesis.pdf", b"%PDF-1.7 fake"), manuscript_revision=revision,
        )
        return PdfExtraction.objects.create(
            record=record, kind=DocumentKind.MANUSCRIPT, source_revision=revision,
            source_file=record.abstract_file.name,
        )

    @pytest.fixture(autouse=True)
    def no_chunking(self, monkeypatch):
        monkeypatch.setattr(tasks, "_queue_chunk_extraction", lambda *args: None)

    def run(self, extraction, monkeypatch, django_capture_on_commit_callbacks, cropped):
        from apps.ai import tasks as ai_tasks

        queued = []
        monkeypatch.setattr(formulas, "crop", lambda pdf, document: cropped(document))
        monkeypatch.setattr(ai_tasks.transcribe_extraction_formulas, "delay", lambda *a: queued.append(a))
        with use_extractor(InMemoryExtractor(formula_document())), \
                django_capture_on_commit_callbacks(execute=True):
            tasks.extract_manuscript_text.apply(args=[extraction.record_id, str(extraction.source_revision)])
        return queued

    def test_each_crop_is_stored_untranscribed_and_transcription_is_queued(
            self, extraction, monkeypatch, django_capture_on_commit_callbacks):
        crop = formulas.PNG + b"crop"
        queued = self.run(extraction, monkeypatch, django_capture_on_commit_callbacks,
                          lambda document: [(formulas.targets(document)[0], crop)])

        (stored,) = extraction.formulas.all()
        assert (stored.name, stored.page, stored.latex, stored.description) == ("eq-1", 1, "", "")
        assert stored.bbox == pytest.approx({"x": 72.0, "y": 144.0, "w": 216.0, "h": 36.0})
        assert stored.source_revision == extraction.source_revision
        with stored.image.open("rb") as image:
            assert image.read() == crop
        assert queued == [(extraction.pk, str(extraction.source_revision))]

    def test_with_no_crop_nothing_is_stored_or_queued(
            self, extraction, monkeypatch, django_capture_on_commit_callbacks):
        queued = self.run(extraction, monkeypatch, django_capture_on_commit_callbacks, lambda document: [])

        assert not extraction.formulas.exists()
        assert queued == []
