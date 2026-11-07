"""The contract suite, run against the in-memory adapter (IR-838).

Also proves the suite can fail: each clause rejects a document that breaks
it, and each committed fixture PDF is what ``layouts.py`` draws today.
"""

from dataclasses import replace
from io import BytesIO

import pytest
from pypdf import PdfReader

from apps.ai.chunking.document import PARAGRAPH, BoundingBox, NormalizedDocument
from apps.ai.extraction import (
    DocumentRejected,
    EmptyExtraction,
    ExtractionError,
    ExtractorUnavailable,
    Failure,
    InMemoryExtractor,
    classify,
)

from .contract import (
    ExtractorContract,
    check_boxes,
    check_pages,
    check_reading_order,
    check_tables,
)
from .fixtures import FIXTURES, expected_document, pdf_bytes, render


class TestInMemoryExtractor(ExtractorContract):
    def extractor_for(self, fixture):
        return InMemoryExtractor(expected_document(fixture))

    def extractor_for_blank(self):
        return InMemoryExtractor(NormalizedDocument(title="", elements=()))

    def extractor_failing_with(self, failure):
        return InMemoryExtractor(ExtractorUnavailable(failure))

    def extractor_rejecting(self):
        return InMemoryExtractor(DocumentRejected("refused"))


@pytest.mark.parametrize("error, failure", [
    (ExtractorUnavailable("down"), Failure.TRANSIENT),
    (DocumentRejected("refused"), Failure.PERMANENT),
    (EmptyExtraction("nothing"), Failure.PERMANENT),
    (ExtractionError("odd body"), Failure.PERMANENT),
    (RuntimeError("a bug"), Failure.PERMANENT),
], ids=["unavailable", "rejected", "empty", "other", "unexpected"])
def test_only_an_unavailable_extractor_is_transient(error, failure):
    assert classify(error) is failure


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_each_committed_pdf_is_what_its_layout_draws(name):
    fixture = FIXTURES[name]
    committed = pdf_bytes(fixture)

    assert committed == render(fixture), "run python -m apps.ai.extraction.tests.fixtures.build"
    assert len(PdfReader(BytesIO(committed)).pages) == len(fixture.pages)


def _fixture_document(name):
    return FIXTURES[name], expected_document(FIXTURES[name])


def test_reading_order_rejects_swapped_columns():
    fixture, document = _fixture_document("two_columns")
    swapped = replace(document, elements=tuple(reversed(document.elements)))

    with pytest.raises(AssertionError, match="reading order"):
        check_reading_order(swapped, fixture)


def test_boxes_reject_a_bottom_left_origin():
    fixture, document = _fixture_document("numbered_headings")
    height = document.page_sizes[1][1]
    flipped = replace(document, elements=tuple(
        replace(e, bboxes=tuple(BoundingBox(b.page, b.left, height - b.bottom, b.right, height - b.top)
                                for b in e.bboxes))
        for e in document.elements
    ))

    with pytest.raises(AssertionError, match="top of the page"):
        check_boxes(flipped, fixture)


def test_boxes_reject_a_box_outside_its_page():
    fixture, document = _fixture_document("figures")
    first = document.elements[0]
    outside = replace(first, bboxes=(BoundingBox(1, 72, 10, 700, 20),))
    broken = replace(document, elements=(outside,) + document.elements[1:])

    with pytest.raises(AssertionError):
        check_boxes(broken, fixture)


def test_pages_reject_numbering_from_zero():
    fixture, document = _fixture_document("numbered_headings")
    zero_based = replace(document, page_sizes={0: (612.0, 792.0), 1: (612.0, 792.0)})

    with pytest.raises(AssertionError):
        check_pages(zero_based, fixture)


def test_tables_reject_a_paragraph_inside_the_table():
    fixture, document = _fixture_document("table_across_pages")
    elements = list(document.elements)
    rows = [i for i, e in enumerate(elements) if e.text.startswith("| Row")]
    elements[rows[10]] = replace(elements[rows[10]], kind=PARAGRAPH)

    with pytest.raises(AssertionError, match="more than one run"):
        check_tables(replace(document, elements=tuple(elements)), fixture)
