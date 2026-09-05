"""The Docling-serve client (IR-107).

Driven through an ``httpx.MockTransport`` rather than a mock object: the
request is really built, really encoded as multipart, and really parsed back.
That is the difference between testing the HTTP contract and testing that we
called a method we wrote.

No container, no Django, no database — so these run everywhere the suite does.
"""

import json

import httpx
import pytest

from apps.ai.chunking.document import HEADING
from apps.ai.extraction.docling_client import EXTRACTOR_NAME, DoclingExtractor
from apps.ai.extraction.ports import (
    EmptyExtraction,
    ExtractionError,
    ExtractorUnavailable,
)

BASE_URL = "http://docling:5001"

_DOCUMENT = {
    "name": "thesis.pdf",
    "pages": {"1": {"size": {"width": 612.0, "height": 792.0}}},
    "texts": [
        {"self_ref": "#/texts/0", "label": "title", "text": "A Thesis"},
        {"self_ref": "#/texts/1", "label": "text", "text": "Body text."},
    ],
    "tables": [],
}


def _extractor(handler, **kwargs) -> DoclingExtractor:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return DoclingExtractor(BASE_URL, client=client, **kwargs)


def _ok(json_content=None, *, status="success"):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "status": status,
                "document": {"json_content": _DOCUMENT if json_content is None else json_content},
            },
        )

    return handler


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------


def test_it_posts_the_pdf_to_the_convert_endpoint():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["body"] = request.content
        return httpx.Response(200, json={"document": {"json_content": _DOCUMENT}})

    _extractor(handler).extract(b"%PDF-1.7 bytes", filename="thesis.pdf")

    assert seen["method"] == "POST"
    assert seen["url"] == f"{BASE_URL}/v1/convert/file"
    assert b"%PDF-1.7 bytes" in seen["body"]
    assert b'filename="thesis.pdf"' in seen["body"]


def test_it_asks_for_ocr_tables_and_structured_output():
    """Each of these is a decision, not a default: OCR is why scanned theses
    work at all, accurate tables are why a table does not retrieve as prose,
    and json is the only format this pipeline reads."""
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode("utf-8", "replace")
        return httpx.Response(200, json={"document": {"json_content": _DOCUMENT}})

    _extractor(handler).extract(b"pdf", filename="thesis.pdf")

    body = seen["body"]
    assert "do_ocr" in body and "true" in body
    assert "do_table_structure" in body
    assert "accurate" in body
    assert "json" in body


def test_a_trailing_slash_on_the_base_url_does_not_double_up():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"document": {"json_content": _DOCUMENT}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    DoclingExtractor(f"{BASE_URL}/", client=client).extract(b"pdf", filename="t.pdf")

    assert seen["url"] == f"{BASE_URL}/v1/convert/file"


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_successful_conversion_returns_the_mapped_document():
    result = _extractor(_ok()).extract(b"pdf", filename="thesis.pdf")

    assert result.extractor == EXTRACTOR_NAME
    assert result.document.title == "A Thesis"
    assert [e.kind for e in result.document.elements][0] == HEADING
    assert result.document.page_sizes == {1: (612.0, 792.0)}


def test_json_content_returned_as_a_string_is_parsed():
    """docling-serve has returned this field both ways across versions."""
    result = _extractor(_ok(json.dumps(_DOCUMENT))).extract(b"pdf", filename="t.pdf")

    assert result.document.title == "A Thesis"


def test_partial_success_is_still_indexed():
    """A document that lost one page to a bad scan is worth having."""
    result = _extractor(_ok(status="partial_success")).extract(b"pdf", filename="t.pdf")

    assert result.document.elements


def test_the_filename_is_the_title_of_last_resort():
    unnamed = {**_DOCUMENT, "name": "", "texts": [{"self_ref": "#/texts/0", "label": "text", "text": "x"}]}

    result = _extractor(_ok(unnamed)).extract(b"pdf", filename="upload-7.pdf")

    assert result.document.title == "upload-7.pdf"


# ---------------------------------------------------------------------------
# Failure
# ---------------------------------------------------------------------------


def test_a_connection_error_is_reported_as_the_extractor_being_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ExtractorUnavailable, match="unreachable"):
        _extractor(handler).extract(b"pdf", filename="t.pdf")


def test_a_timeout_is_reported_as_the_extractor_being_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ExtractorUnavailable, match="did not respond"):
        _extractor(handler, timeout=30.0).extract(b"pdf", filename="t.pdf")


def test_a_5xx_is_the_service_failing_not_the_document():
    def handler(request):
        return httpx.Response(503, text="upstream unavailable")

    with pytest.raises(ExtractorUnavailable, match="503"):
        _extractor(handler).extract(b"pdf", filename="t.pdf")


def test_a_4xx_is_the_document_being_rejected():
    def handler(request):
        return httpx.Response(413, text="file too large")

    with pytest.raises(ExtractionError) as caught:
        _extractor(handler).extract(b"pdf", filename="t.pdf")

    assert not isinstance(caught.value, ExtractorUnavailable)
    assert "413" in str(caught.value)


def test_a_reported_failure_status_carries_the_service_errors_through():
    def handler(request):
        return httpx.Response(
            200, json={"status": "failure", "errors": ["page limit exceeded"], "document": {}}
        )

    with pytest.raises(ExtractionError, match="page limit exceeded"):
        _extractor(handler).extract(b"pdf", filename="t.pdf")


def test_a_markdown_only_response_is_a_failure():
    """Structure is the point of this call. Silently accepting the flat text
    is exactly the regression ADR-016 exists to prevent."""

    def handler(request):
        return httpx.Response(200, json={"document": {"md_content": "# A Thesis"}})

    with pytest.raises(ExtractionError, match="no structured content"):
        _extractor(handler).extract(b"pdf", filename="t.pdf")


def test_a_non_json_body_is_a_failure():
    def handler(request):
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(ExtractionError, match="non-JSON"):
        _extractor(handler).extract(b"pdf", filename="t.pdf")


def test_a_document_with_no_extractable_content_is_a_failure():
    """An upload that indexes to zero chunks is invisible to search and looks
    identical to one that was never uploaded."""
    empty = {"name": "t.pdf", "pages": {}, "texts": [], "tables": []}

    with pytest.raises(EmptyExtraction):
        _extractor(_ok(empty)).extract(b"pdf", filename="t.pdf")


def test_every_failure_is_an_extraction_error():
    """The task catches one type. Anything that escapes it as an httpx
    exception would be persisted as an unreadable error string."""
    assert issubclass(ExtractorUnavailable, ExtractionError)
    assert issubclass(EmptyExtraction, ExtractionError)


def test_the_connect_timeout_is_short_even_when_the_read_budget_is_long():
    """A conversion may legitimately take ten minutes; opening a socket never
    does. Sharing one value would hang an unreachable host for the whole
    read budget."""
    timeouts = DoclingExtractor(BASE_URL, timeout=600.0)._timeouts()

    assert timeouts.read == 600.0
    assert timeouts.connect < 60.0


def test_the_configured_timeout_applies_to_an_injected_client_too():
    """Setting it on the client would leave every injected client — every
    test, and any caller passing a pooled one — on its own budget."""
    seen = {}

    def handler(request):
        seen["timeout"] = request.extensions.get("timeout")
        return httpx.Response(200, json={"document": {"json_content": _DOCUMENT}})

    _extractor(handler, timeout=123.0).extract(b"pdf", filename="t.pdf")

    assert seen["timeout"]["read"] == 123.0
