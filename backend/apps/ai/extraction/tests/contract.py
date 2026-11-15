"""The contract every non-legacy Extractor honours (IR-838).

Subclass ``ExtractorContract`` and implement its three hooks; pytest then
runs the clauses against that adapter over the synthetic fixtures. The
in-memory adapter runs it here, and IR-841 adds LlamaParse. Docling is
legacy (ADR-056) and is not held to it.
"""

import pytest

from apps.ai.chunking.document import (
    PAGE_FOOTER,
    PAGE_HEADER,
    TABLE_HEADER,
    TABLE_ROW,
    NormalizedDocument,
)
from apps.ai.extraction import (
    DocumentRejected,
    EmptyExtraction,
    ExtractorUnavailable,
    Failure,
    StructuredExtractor,
    classify,
)

from .fixtures import FIXTURES, Fixture, blank_pdf, pdf_bytes

# Points of slack for an Extractor that rounds coordinates.
TOLERANCE = 0.5
FAILURES = ("connect", "timeout", "5xx")
# Shapers on the labeled structure emit "header"/"footer"/"table" (IR-840, IR-986).
FURNITURE = {PAGE_HEADER, PAGE_FOOTER, "header", "footer"}
TABLE = {TABLE_HEADER, TABLE_ROW, "table"}


def check_reading_order(document: NormalizedDocument, fixture: Fixture) -> None:
    texts = [e.text for e in document.elements]
    positions = []
    for marker in fixture.reading_order:
        found = [i for i, text in enumerate(texts) if marker in text]
        assert found, f"{marker!r} is missing from the {fixture.name} extraction"
        positions.append(found[0])
    assert positions == sorted(positions), (
        f"{fixture.name} is out of reading order: {fixture.reading_order}"
    )


def check_boxes(document: NormalizedDocument, fixture: Fixture) -> None:
    for element in document.elements:
        assert element.bboxes, f"{element.text!r} has no box to highlight"
        for box in element.bboxes:
            width, height = document.page_sizes[box.page]
            assert -TOLERANCE <= box.left < box.right <= width + TOLERANCE, element.text
            assert -TOLERANCE <= box.top < box.bottom <= height + TOLERANCE, element.text
    # Top-left origin: of two passages in one column, the one read first sits higher.
    boxes = [next(e.bbox for e in document.elements if marker in e.text)
             for marker in fixture.reading_order]
    pairs = [(a, b) for a, b in zip(boxes, boxes[1:])
             if a.page == b.page and abs(a.left - b.left) <= TOLERANCE]
    assert pairs, f"{fixture.name} has no two markers in one column to compare"
    assert all(a.top < b.top for a, b in pairs), "boxes are not measured from the top of the page"


def check_pages(document: NormalizedDocument, fixture: Fixture) -> None:
    count = len(fixture.pages)
    assert set(document.page_sizes) == set(range(1, count + 1))
    assert all(w > 0 and h > 0 for w, h in document.page_sizes.values())
    for element in document.elements:
        assert element.page in document.page_sizes, element.text
        assert all(box.page in document.page_sizes for box in element.bboxes), element.text


def check_tables(document: NormalizedDocument, fixture: Fixture) -> None:
    if not fixture.has_table:
        return
    kinds = [e.kind for e in document.elements if e.kind not in FURNITURE]
    tabular = [i for i, kind in enumerate(kinds) if kind in TABLE]
    assert tabular, f"{fixture.name} has a table and none arrived"
    assert tabular == list(range(tabular[0], tabular[-1] + 1)), (
        "the table arrived in more than one run"
    )


CLAUSES = (check_reading_order, check_boxes, check_pages, check_tables)


class ExtractorContract:
    def extractor_for(self, fixture: Fixture) -> StructuredExtractor:
        """An adapter that will read ``fixture``'s PDF."""
        raise NotImplementedError

    def extractor_for_blank(self) -> StructuredExtractor:
        """An adapter that will read ``blank_pdf()``."""
        raise NotImplementedError

    def extractor_failing_with(self, failure: str) -> StructuredExtractor:
        """An adapter whose service fails by ``failure``: one of ``FAILURES``."""
        raise NotImplementedError

    def extractor_rejecting(self) -> StructuredExtractor:
        """An adapter whose service reads ``blank_pdf()`` and refuses it (IR-839)."""
        raise NotImplementedError

    @pytest.mark.parametrize("clause", CLAUSES, ids=lambda c: c.__name__[len("check_"):])
    @pytest.mark.parametrize("name", sorted(FIXTURES))
    def test_clause(self, name, clause):
        fixture = FIXTURES[name]
        extracted = self.extractor_for(fixture).extract(pdf_bytes(fixture), filename=fixture.filename)
        clause(extracted.document, fixture)

    def test_an_empty_pdf_is_an_empty_extraction(self):
        with pytest.raises(EmptyExtraction) as raised:
            self.extractor_for_blank().extract(blank_pdf(), filename="blank.pdf")
        assert classify(raised.value) is Failure.PERMANENT

    @pytest.mark.parametrize("failure", FAILURES)
    def test_a_failing_service_is_unavailable(self, failure):
        with pytest.raises(ExtractorUnavailable) as raised:
            self.extractor_failing_with(failure).extract(blank_pdf(), filename="any.pdf")
        assert classify(raised.value) is Failure.TRANSIENT

    def test_a_rejected_document_is_permanent(self):
        with pytest.raises(DocumentRejected) as raised:
            self.extractor_rejecting().extract(blank_pdf(), filename="any.pdf")
        assert classify(raised.value) is Failure.PERMANENT

    def test_a_declared_timeout(self):
        timeout = self.extractor_for_blank().timeout_seconds
        assert isinstance(timeout, (int, float)) and timeout > 0
