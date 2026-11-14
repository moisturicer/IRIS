"""The Unstructured Extractor, replaying Platform ``hi_res`` recordings (IR-985, ADR-067)."""

import json

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.ai.chunking.document import PARAGRAPH, BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.extraction import (
    DocumentRejected,
    EmptyExtraction,
    ExtractionError,
    ExtractorUnavailable,
    Failure,
    classify,
)
from apps.ai.extraction.shaping_unstructured import shape_unstructured
from apps.ai.extraction.unstructured_client import UnstructuredExtractor

from .contract import ExtractorContract
from .fixtures import FIXTURES, blank_pdf, pdf_bytes
from .unstructured_platform_vendor import API_KEY, Vendor, recording


def first_text(raw: dict) -> NormalizedDocument:
    """Stands in for IR-986's shaping: the first element's text, as a paragraph."""
    return NormalizedDocument(
        title="",
        elements=(DocumentElement(kind=PARAGRAPH, text=raw["elements"][0]["text"],
                                  bboxes=(BoundingBox(1, 0, 0, 10, 10),)),),
        page_sizes={1: (612.0, 792.0)},
    )


def extractor(vendor: Vendor, **overrides) -> UnstructuredExtractor:
    options = dict(api=vendor.api(), api_key=API_KEY, shape=first_text, sleep=lambda seconds: None)
    options.update(overrides)
    return UnstructuredExtractor(**options)


def read(vendor: Vendor, name: str = "two_columns", **overrides):
    fixture = FIXTURES[name]
    return extractor(vendor, **overrides).extract(pdf_bytes(fixture), filename=fixture.filename)


def test_a_recorded_partition_returns_raw_usage_and_provenance():
    vendor = Vendor("two_columns")

    extracted = read(vendor)

    assert extracted.document.elements[0].text == "IRIS contract fixture"
    assert extracted.raw["elements"] == recording("two_columns")
    assert extracted.usage.pages == 1
    assert extracted.usage.credits is None
    assert extracted.failed_pages == ()
    assert extracted.provenance.name == "unstructured"
    assert extracted.provenance.version == "general/v0:hi_res"
    assert extracted.provenance.options["strategy"] == "hi_res"
    assert extracted.provenance.options["call"] == {"mode": "synchronous", "attempts": 2, "attempts_made": 1,
                                                     "attempt_timeout_seconds": 130.0}


def test_the_request_is_the_amended_hi_res_partition():
    vendor = Vendor("two_columns")

    read(vendor)

    request = vendor.requests[0]
    body = vendor.form()
    assert request.url.path == "/general/v0/general"
    assert request.headers["unstructured-api-key"] == API_KEY
    for field, value in (("strategy", "hi_res"), ("coordinates", "true"),
                         ("pdf_infer_table_structure", "true"), ("include_page_breaks", "true")):
        assert f'name="{field}"\r\n\r\n{value}'.encode() in body
    assert b'["Image", "Table"]' in body
    assert b'filename="two_columns.pdf"' in body


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_recording_replays(name):
    extracted = read(Vendor(name), name)

    assert extracted.raw["elements"] == recording(name)
    assert extracted.usage.pages == len(FIXTURES[name].pages)


def test_the_attempt_timeout_grows_with_the_page_count():
    vendor = Vendor("table_across_pages")

    read(vendor, "table_across_pages", timeout_base_seconds=100, timeout_per_page_seconds=7)

    assert vendor.requests[0].extensions["timeout"]["read"] == 114


def test_a_timed_out_call_is_retried_once():
    vendor = Vendor("two_columns", answers=(httpx.ReadTimeout("slow"),))

    extracted = read(vendor)

    assert len(vendor.requests) == 2
    assert extracted.raw["elements"] == recording("two_columns")
    assert extracted.provenance.options["call"]["attempts_made"] == 2


def test_a_second_timeout_is_unavailable():
    vendor = Vendor("two_columns", answers=(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slower")))

    with pytest.raises(ExtractorUnavailable) as raised:
        read(vendor)

    assert len(vendor.requests) == 2
    assert classify(raised.value) is Failure.TRANSIENT


def test_only_a_timeout_is_retried_in_the_client():
    vendor = Vendor("two_columns", answers=(httpx.ConnectError("refused"),))

    with pytest.raises(ExtractorUnavailable):
        read(vendor)

    assert len(vendor.requests) == 1


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500, 502, 503, 504])
def test_a_deployment_or_vendor_fault_is_unavailable(status):
    vendor = Vendor("two_columns", answers=(httpx.Response(status, json={"detail": "no"}),))

    with pytest.raises(ExtractorUnavailable):
        read(vendor)


def test_the_recorded_refusal_of_a_broken_pdf_is_permanent():
    vendor = Vendor("rejected")

    with pytest.raises(DocumentRejected, match="valid PDF") as raised:
        read(vendor)

    assert classify(raised.value) is Failure.PERMANENT


@pytest.mark.parametrize("status", [400, 413, 415, 422])
def test_a_document_fault_is_rejected(status):
    vendor = Vendor("two_columns", answers=(httpx.Response(status, json={"detail": "bad file"}),))

    with pytest.raises(DocumentRejected):
        read(vendor)


def test_a_refused_request_parameter_is_not_the_documents_fault():
    detail = [{"loc": ["body", "strategy"], "msg": "bad value", "type": "value_error"}]
    vendor = Vendor("two_columns", answers=(httpx.Response(422, json={"detail": detail}),))

    with pytest.raises(ExtractionError) as raised:
        read(vendor)

    assert not isinstance(raised.value, (DocumentRejected, ExtractorUnavailable))
    assert classify(raised.value) is Failure.PERMANENT


def test_a_link_with_sig_in_its_path_is_kept():
    elements = recording("two_columns")
    elements[0]["metadata"]["links"] = [{"url": "https://example.org/design-sig=1", "text": "x"}]

    extracted = read(Vendor("two_columns", result=elements))

    assert "design-sig=1" in json.dumps(extracted.raw)


def test_a_blank_pdf_is_an_empty_extraction():
    vendor = Vendor("blank")

    with pytest.raises(EmptyExtraction):
        extractor(vendor).extract(blank_pdf(), filename="blank.pdf")


def test_an_answer_that_is_not_an_element_list_is_unavailable():
    vendor = Vendor("two_columns", answers=(httpx.Response(200, json={"elements": []}),))

    with pytest.raises(ExtractorUnavailable):
        read(vendor)


def test_an_unreadable_pdf_is_rejected_before_anything_is_sent():
    vendor = Vendor("two_columns")

    with pytest.raises(DocumentRejected):
        extractor(vendor).extract(b"not a pdf", filename="x.pdf")

    assert vendor.requests == []


def test_no_key_or_signed_url_reaches_raw():
    elements = recording("two_columns")
    elements[0]["metadata"]["presigned_url"] = "https://bucket.test/x?X-Amz-Signature=abc"
    elements[1]["metadata"]["image_url"] = "https://bucket.test/y?X-Amz-Credential=k&Signature=s"
    elements[2]["metadata"]["links"] = [{"url": "https://doi.org/10.1/x", "text": "doi"}]

    extracted = read(Vendor("two_columns", result=elements))

    stored = json.dumps(extracted.raw)
    assert "presigned_url" not in stored and "Signature" not in stored
    assert API_KEY not in stored
    assert "https://doi.org/10.1/x" in stored


def test_admission_can_name_the_model_and_the_account():
    from apps.ai.admission.ledger import account_for

    adapter = extractor(Vendor(), api_key="key-one")

    assert adapter.leaves_campus is True
    assert adapter.model == "unstructured-hi_res"
    assert adapter.account == account_for("key-one")
    assert adapter.account != extractor(Vendor(), api_key="key-two").account


def test_the_declared_timeout_covers_every_attempt_at_the_page_ceiling():
    adapter = extractor(Vendor(), timeout_base_seconds=100, timeout_per_page_seconds=10, max_pages=50)

    assert adapter.timeout_seconds >= 2 * (100 + 10 * 50)


FAILURES = {
    "connect": httpx.ConnectError("refused"),
    "timeout": httpx.ReadTimeout("slow"),
    "5xx": httpx.Response(502),
}


_FORMULA = "hi_res Formula OCR is withheld until transcribed (ADR-067 formula amendment)"
_TABLE = "hi_res reads one-column rows and leaves page 2's rows as text; IR-989 judges tables"
# Strict: each flips to a failure when the gap closes.
KNOWN_GAPS = {
    ("two_columns", "check_reading_order"): "hi_res misorders this fixture (ADR-067 amendment §3)",
    ("figures", "check_reading_order"): _FORMULA,
    ("figures", "check_boxes"): _FORMULA,
    ("table_across_pages", "check_reading_order"): _TABLE,
    ("table_across_pages", "check_boxes"): _TABLE,
}


class TestUnstructuredContract(ExtractorContract):
    @pytest.fixture(autouse=True)
    def _known_gaps(self, request):
        params = getattr(getattr(request.node, "callspec", None), "params", {})
        reason = KNOWN_GAPS.get((params.get("name"), getattr(params.get("clause"), "__name__", "")))
        if reason:
            request.applymarker(pytest.mark.xfail(strict=True, reason=reason))

    def extractor_for(self, fixture):
        return extractor(Vendor(fixture.name), shape=shape_unstructured)

    def extractor_for_blank(self):
        return extractor(Vendor("blank"))

    def extractor_failing_with(self, failure):
        answer = FAILURES[failure]
        return extractor(Vendor("two_columns", answers=(answer, answer)))

    def extractor_rejecting(self):
        return extractor(Vendor("rejected"))


class TestBuilder:
    def test_a_missing_key_refuses_and_names_it(self, settings):
        from apps.ai.extraction.selection import unstructured_extractor

        settings.UNSTRUCTURED_PLATFORM_API_KEY = ""

        with pytest.raises(ImproperlyConfigured, match="UNSTRUCTURED_PLATFORM_API_KEY"):
            unstructured_extractor()

    def test_another_host_is_refused(self, settings):
        from apps.ai.extraction.selection import unstructured_extractor

        settings.UNSTRUCTURED_PLATFORM_API_KEY = "configured"
        settings.UNSTRUCTURED_BASE_URL = "https://transform.unstructured.io"

        with pytest.raises(ImproperlyConfigured, match="UNSTRUCTURED_BASE_URL"):
            unstructured_extractor()

    def test_a_configured_builder_returns_the_adapter(self, settings):
        from apps.ai.extraction.selection import unstructured_extractor

        settings.UNSTRUCTURED_PLATFORM_API_KEY = "configured"
        settings.UNSTRUCTURED_BASE_URL = "https://api.unstructuredapp.io"

        adapter = unstructured_extractor()
        vendor = Vendor("numbered_headings")
        adapter._api = vendor.api()
        fixture = FIXTURES["numbered_headings"]
        extracted = adapter.extract(pdf_bytes(fixture), filename=fixture.filename)

        assert isinstance(adapter, UnstructuredExtractor)
        assert adapter.leaves_campus is True
        assert extracted.document.elements[1].text == "1 Introduction"

    def test_it_is_not_a_selectable_backend_before_the_cutover(self, settings):
        from apps.ai.extraction.selection import verify_extraction_configuration

        settings.EXTRACTION_BACKEND = "unstructured"

        with pytest.raises(ImproperlyConfigured, match="EXTRACTION_BACKEND"):
            verify_extraction_configuration()
