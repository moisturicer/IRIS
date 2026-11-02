"""Stored Extraction reads use today's shaping, never yesterday's derived copy."""

from apps.ai.extraction.tests.test_shaping import result_with
from apps.ai.extraction import document_to_json, shape_llamaparse
from apps.documents.models import PdfExtraction

import json


def test_raw_llamaparse_result_is_reshaped_for_document_and_search_reads():
    extraction = PdfExtraction(extractor="llamaparse", structure={
        "elements": [{"kind": "paragraph", "text": "Stale cached structure"}],
    })
    # IR-841 owns this additive storage field. IR-840 consumes its contract.
    extraction.raw_result = result_with([
        {"type": "header", "value": "Running chrome"},
        {"type": "text", "value": "123"},
        {"type": "text", "value": "Original prose."},
    ])
    document = extraction.as_normalized_document()
    assert document.structure_is_authoritative
    assert extraction.as_search_text() == "123 Original prose."
    extraction.raw_result["items"]["pages"][0]["items"][2]["value"] = "Revised prose."
    assert extraction.as_search_text() == "123 Revised prose."
    assert extraction.as_normalized_document().elements[-1].text == "Revised prose."


def test_llamaparse_without_raw_result_refuses_a_stale_structure():
    extraction = PdfExtraction(extractor="llamaparse", structure={
        "elements": [{"kind": "paragraph", "text": "Stale cached structure"}],
    })
    assert extraction.as_normalized_document() is None
    assert extraction.as_search_text() == ""


def test_serialized_document_keeps_authoritative_structure_and_evidence():
    document = shape_llamaparse(result_with([
        {"type": "list", "ordered": True, "items": [{"type": "text", "value": "Nested item"}]},
        {"type": "table", "rows": [["Name"], ["A"]], "html": "<table>kept</table>"},
        {"type": "other_label", "value": "Unknown label stays"},
    ]))
    structure = json.loads(json.dumps(document_to_json(document)))
    extraction = PdfExtraction(extractor="in_memory", structure=structure)
    assert extraction.as_normalized_document() == document
