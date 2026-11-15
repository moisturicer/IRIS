"""A stored Extraction is read from its stored structure (IR-988, ADR-067)."""

import json

from apps.ai.chunking.document import DocumentElement, NormalizedDocument
from apps.ai.extraction import document_to_json
from apps.documents.models import PdfExtraction

STRUCTURE = {"elements": [{"kind": "paragraph", "text": "Stored structure"}]}


def test_a_llamaparse_read_is_read_from_its_stored_structure_not_reshaped():
    extraction = PdfExtraction(extractor="llamaparse", structure=STRUCTURE)
    extraction.raw_result = {"items": {"pages": [{"page_number": 1, "items": [{"type": "text", "value": "Raw"}]}]}}

    assert extraction.as_search_text() == "Stored structure"
    assert [e.text for e in extraction.as_normalized_document().elements] == ["Stored structure"]


def test_an_extraction_with_no_structure_reads_as_nothing():
    extraction = PdfExtraction(extractor="unstructured", structure={})

    assert extraction.as_normalized_document() is None
    assert extraction.as_search_text() == ""


def test_serialized_document_keeps_authoritative_structure_and_evidence():
    document = NormalizedDocument(
        title="A paper",
        elements=(
            DocumentElement(kind="list", text="1. Nested item", page=1, ordered=True,
                            children=(DocumentElement(kind="text", text="Nested item", page=1),)),
            DocumentElement(kind="table", text="Name\nA", page=1, rows=(("Name",), ("A",)),
                            html="<table>kept</table>"),
        ),
        page_sizes={1: (612.0, 792.0)},
        structure_is_authoritative=True,
    )
    structure = json.loads(json.dumps(document_to_json(document)))
    extraction = PdfExtraction(extractor="unstructured", structure=structure)

    assert extraction.as_normalized_document() == document
