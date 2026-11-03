"""The LlamaParse Extractor, replaying IR-849's recordings over HTTP (IR-841)."""

import json
from decimal import Decimal

import httpx
import pytest

from apps.ai.chunking.document import PARAGRAPH, BoundingBox, DocumentElement, NormalizedDocument
from apps.ai.extraction import (
    DocumentRejected,
    ExtractionError,
    ExtractorUnavailable,
    Failure,
    classify,
)
from apps.ai.extraction import llamaparse_client
from apps.ai.extraction.llamaparse_client import LlamaParseExtractor

from .contract import ExtractorContract
from .fixtures import FIXTURES, pdf_bytes
from .llamaparse_vendor import Vendor, no_sleep, recording

VERSION = "2026-09-28"


def one_paragraph(raw: dict) -> NormalizedDocument:
    """Stands in for IR-840's shaping: the first heading's value, as a paragraph."""
    first = raw["items"]["pages"][0]["items"][1]
    return NormalizedDocument(
        title="",
        elements=(DocumentElement(kind=PARAGRAPH, text=first["value"],
                                  bboxes=(BoundingBox(1, 0, 0, 10, 10),)),),
        page_sizes={1: (612.0, 792.0)},
    )


def extractor(vendor: Vendor, **overrides) -> LlamaParseExtractor:
    options = dict(
        api=vendor.api(), downloads=vendor.downloads(), version=VERSION,
        shape=one_paragraph, sleep=no_sleep, remember_timeout=lambda key: True,
    )
    options.update(overrides)
    return LlamaParseExtractor(**options)


def read(vendor: Vendor, name: str, **overrides):
    fixture = FIXTURES[name]
    return extractor(vendor, **overrides).extract(pdf_bytes(fixture), filename=fixture.filename)


def test_a_recorded_parse_returns_the_raw_result_its_usage_and_provenance():
    vendor = Vendor("numbered_headings")

    extracted = read(vendor, "numbered_headings")

    assert extracted.document.elements[0].text == "1 Introduction"
    assert extracted.raw["job"]["id"] == "pjb-fo9lwvmpo69v2ypfur9asmd57g6z"
    assert extracted.raw["metadata"]["pages"][1]["printed_page_number"] == "2"
    assert extracted.raw["grounded_items"][0]["page_width"] == 612
    assert extracted.usage.pages == 2
    assert extracted.usage.credits == Decimal("30.0")
    assert extracted.provenance.name == "llamaparse"
    assert extracted.provenance.version == VERSION
    assert extracted.provenance.options["tier"] == "agentic"
    assert vendor.deleted == ["dfl-recorded"]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_recording_replays(name):
    extracted = read(Vendor(name), name)

    assert extracted.raw["job"]["status"] == "COMPLETED"
    assert extracted.raw["grounded_items"]


def test_the_request_asks_for_everything_and_times_out_by_page_count():
    vendor = Vendor("table_across_pages")

    read(vendor, "table_across_pages", timeout_base_seconds=100, timeout_per_page_seconds=7)

    sent = vendor.created
    assert sent["file_id"] == "dfl-recorded"
    assert (sent["tier"], sent["version"], sent["disable_cache"]) == ("agentic", VERSION, True)
    assert sent["processing_options"] == {
        "cost_optimizer": {"enable": True},
        "confidence_score_effort": "high",
        "specialized_chart_parsing": "agentic",
    }
    assert sent["output_options"]["granular_bboxes"] == ["word", "line", "cell"]
    assert sent["output_options"]["extract_printed_page_number"] is True
    assert sent["output_options"]["markdown"]["tables"]["merge_continued_tables"] is True
    assert sent["output_options"]["images_to_save"] == ["layout"]
    assert sent["processing_control"]["timeouts"] == {
        "base_in_seconds": 100, "extra_time_per_page_in_seconds": 7,
    }
    assert "webhook_configurations" not in sent
    fetch = next(r for r in vendor.requests if "expand" in r.url.params)
    assert {"items", "markdown", "metadata"} <= set(fetch.url.params["expand"].split(","))


class Clock:
    """Wall time that advances by each sleep plus a slow poll."""

    def __init__(self, per_poll=0.0):
        self.now = 0.0
        self.per_poll = per_poll

    def __call__(self):
        self.now += self.per_poll
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_a_job_is_abandoned_once_its_page_sized_budget_is_spent_on_the_wall_clock():
    vendor = Vendor("figures", statuses=("RUNNING",))
    clock = Clock(per_poll=5.0)

    with pytest.raises(ExtractorUnavailable):
        read(vendor, "figures", timeout_base_seconds=10, timeout_per_page_seconds=4,
             clock=clock, sleep=clock.sleep)

    polls = [r for r in vendor.requests if r.method == "GET" and "expand" not in r.url.params]
    assert 14 < clock.now < 14 + llamaparse_client.POLL_GRACE_SECONDS + 10
    assert len(polls) < 14 + llamaparse_client.POLL_GRACE_SECONDS
    assert vendor.deleted == ["dfl-recorded"]


def test_the_declared_timeout_covers_the_largest_accepted_pdf():
    adapter = extractor(Vendor("figures"), timeout_base_seconds=300,
                        timeout_per_page_seconds=30, max_pages=1000)

    assert adapter.timeout_seconds >= 300 + 30 * 1000
    assert adapter.leaves_campus is True


def test_the_stored_result_keeps_what_shaping_needs():
    raw = read(Vendor("table_across_pages"), "table_across_pages").raw

    table = next(i for i in raw["items"]["pages"][0]["items"] if i["type"] == "table")
    assert table["merged_from_pages"] == [1, 2]
    assert table["parse_concerns"][0]["type"] == "layout_lvm_disagreement"
    page = raw["metadata"]["pages"][0]
    assert {"confidence", "printed_page_number", "cost_optimized", "original_orientation_angle"} <= set(page)
    assert raw["metadata"]["document"]["confidence_breakdown"]["total_pages"] == 2
    assert raw["job"]["usage"]["credits"] == 33.0
    assert "grounding" in raw["grounded_items"][0]["items"][0]["items"][0]
    assert "presigned_url" not in json.dumps(raw)


def test_credits_billed_after_completion_are_waited_for():
    vendor = Vendor("two_columns", credits_after=1)

    extracted = read(vendor, "two_columns")

    assert vendor.fetches == 2
    assert extracted.usage.credits == Decimal("15.0")


def test_credits_never_reported_are_none_rather_than_lost():
    extracted = read(Vendor("two_columns", credits_after=99), "two_columns")

    assert extracted.usage.credits is None
    assert extracted.usage.pages == 1


def test_failed_pages_are_reported_and_the_rest_kept():
    result = recording("numbered_headings")
    result["items"]["pages"][1] = {"page_number": 2, "success": False, "error": "x"}

    extracted = read(Vendor("numbered_headings", result=result), "numbered_headings")

    assert extracted.failed_pages == (2,)


@pytest.mark.parametrize("step, answer", [
    ("upload", httpx.ConnectError("refused")),
    ("create", httpx.ReadTimeout("slow")),
    ("poll", httpx.Response(429)),
    ("fetch", httpx.Response(503)),
], ids=["unreachable", "timeout", "429", "5xx"])
def test_a_failing_service_is_unavailable(step, answer):
    vendor = Vendor("figures", failure=(step, answer))

    with pytest.raises(ExtractorUnavailable) as raised:
        read(vendor, "figures")

    assert classify(raised.value) is Failure.TRANSIENT
    assert vendor.deleted == ([] if step == "upload" else ["dfl-recorded"])


@pytest.mark.parametrize("status", [401, 402, 403])
def test_a_key_or_account_fault_is_not_the_documents(status):
    vendor = Vendor("figures", failure=("create", httpx.Response(status, json={"detail": "no"})))

    with pytest.raises(ExtractorUnavailable):
        read(vendor, "figures")


def test_an_expired_download_link_is_not_the_documents_fault():
    vendor = Vendor("figures", failure=("download", httpx.Response(403)))

    with pytest.raises(ExtractorUnavailable):
        read(vendor, "figures")

    assert vendor.deleted == ["dfl-recorded"]


@pytest.mark.parametrize("status", [400, 404, 413, 422])
def test_another_4xx_is_a_rejected_document(status):
    vendor = Vendor("figures", failure=("create", httpx.Response(status, json={"detail": "no"})))

    with pytest.raises(DocumentRejected):
        read(vendor, "figures")

    assert vendor.deleted == ["dfl-recorded"]


@pytest.mark.parametrize("code", [
    "DOCUMENT_TOO_LARGE", "PROCESSING_SIZE_LIMIT_EXCEEDED", "CONTENT_POLICY_REFUSAL",
])
def test_a_job_the_vendor_refuses_is_rejected(code):
    vendor = Vendor("figures", statuses=("FAILED",), error_message=f"{code}: refused")

    with pytest.raises(DocumentRejected) as raised:
        read(vendor, "figures")

    assert classify(raised.value) is Failure.PERMANENT
    assert vendor.deleted == ["dfl-recorded"]


def test_a_first_job_timeout_retries_and_a_second_is_the_documents_fault():
    seen = set()

    def first(key):
        fresh = key not in seen
        seen.add(key)
        return fresh

    for expected in (ExtractorUnavailable, DocumentRejected):
        vendor = Vendor("figures", statuses=("FAILED",), error_message="TIMEOUT: too slow")
        with pytest.raises(expected):
            read(vendor, "figures", remember_timeout=first)


def test_a_conversion_timeout_is_not_mistaken_for_a_job_timeout():
    vendor = Vendor("figures", statuses=("FAILED",), error_message="DOCUMENT_CONVERSION_TIMEOUT")

    with pytest.raises(ExtractionError) as raised:
        read(vendor, "figures")

    assert classify(raised.value) is Failure.PERMANENT


def test_a_layout_figure_is_downloaded_with_its_page_and_caption():
    result = recording("figures")
    result["items"]["pages"][0]["items"].append(
        {"type": "image", "url": "image_0.png", "caption": "Figure 1: A captioned rectangle.",
         "bbox": [{"x": 72, "y": 300, "w": 200, "h": 100}]})
    result["images_content_metadata"] = {"total_count": 2, "images": [
        {"index": 0, "filename": "image_0.png", "category": "layout", "content_type": "image/png",
         "bbox": {"x": 72, "y": 300, "w": 200, "h": 100}},
        {"index": 1, "filename": "page_1.jpg", "category": "screenshot", "content_type": "image/jpeg",
         "bbox": {"x": 0, "y": 0, "w": 612, "h": 792}},
    ]}
    vendor = Vendor("figures", result=result, images={"image_0.png": b"\x89PNG crop"})

    extracted = read(vendor, "figures")

    (figure,) = extracted.figures
    assert (figure.page, figure.media_type, figure.data) == (1, "image/png", b"\x89PNG crop")
    assert figure.caption == "Figure 1: A captioned rectangle."
    assert figure.bbox == {"x": 72, "y": 300, "w": 200, "h": 100}
    downloads = [r for r in vendor.requests if r.url.host == "downloads.vendor.test"]
    assert "/images/page_1.jpg" not in [r.url.path for r in downloads]
    assert all("authorization" not in r.headers for r in downloads)
    order = [(r.method, r.url.host) for r in vendor.requests]
    assert order[-1] == ("DELETE", "api.vendor.test")


@pytest.fixture
def logged(caplog):
    """``apps`` loggers do not propagate, so capture this one directly."""
    llamaparse_client.logger.addHandler(caplog.handler)
    yield caplog
    llamaparse_client.logger.removeHandler(caplog.handler)


def test_a_refused_delete_does_not_hide_the_result(logged):
    vendor = Vendor("figures", failure=("delete", httpx.Response(500)))

    extracted = read(vendor, "figures")

    assert extracted.raw["job"]["status"] == "COMPLETED"
    assert "may remain" in logged.text


def test_a_failed_job_keeps_its_own_error_when_the_delete_fails_too(logged):
    vendor = Vendor("figures", statuses=("FAILED",), error_message="PDF_IS_BROKEN",
                    failure=("delete", httpx.Response(500)))

    with pytest.raises(DocumentRejected):
        read(vendor, "figures")

    assert "may remain" in logged.text


FAILURES = {
    "connect": ("upload", httpx.ConnectError("refused")),
    "timeout": ("poll", httpx.ReadTimeout("slow")),
    "5xx": ("fetch", httpx.Response(502)),
}


class TestLlamaParseContract(ExtractorContract):
    def extractor_for(self, fixture):
        pytest.skip("the document clauses need IR-840's shaping of LlamaParse's result")

    def extractor_for_blank(self):
        return extractor(Vendor("figures", statuses=("FAILED",), error_message="NO_DATA_FOUND_IN_FILE"))

    def extractor_failing_with(self, failure):
        return extractor(Vendor("figures", failure=FAILURES[failure]))

    def extractor_rejecting(self):
        return extractor(Vendor("figures", statuses=("FAILED",), error_message="DOCUMENT_TOO_LARGE"))


def test_admission_can_name_the_model_and_the_account():
    from apps.ai.admission.ledger import account_for

    adapter = extractor(Vendor("figures"), api_key="llx-one", tier="agentic")

    assert adapter.model == "llamaparse-agentic"
    assert adapter.account == account_for("llx-one")
    assert adapter.account != extractor(Vendor("figures"), api_key="llx-two").account
