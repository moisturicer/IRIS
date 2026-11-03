"""LlamaExtract reading a completed LlamaParse job, over HTTP (IR-846).

Authored payloads, not recordings: see ``llamaextract_vendor``.
"""

from decimal import Decimal

import httpx
import pytest

from apps.ai.extraction import ExtractionError, ExtractorUnavailable
from apps.ai.extraction.llamaextract_client import SCHEMA, LlamaExtractReader

from .llamaextract_vendor import PARSE_JOB_ID, Vendor
from .llamaparse_vendor import no_sleep

VERSION = "2.5"


def reader(vendor: Vendor, **overrides) -> LlamaExtractReader:
    options = dict(api=vendor.api(), version=VERSION, sleep=no_sleep)
    options.update(overrides)
    return LlamaExtractReader(**options)


def test_it_reads_the_parse_job_with_one_fixed_schema_citations_and_confidence():
    vendor = Vendor()

    reading = reader(vendor).read(PARSE_JOB_ID)

    assert vendor.created == {
        "file_input": PARSE_JOB_ID,
        "configuration": {
            "tier": "agentic",
            "version": VERSION,
            "extraction_target": "per_doc",
            "data_schema": SCHEMA,
            "cite_sources": True,
            "confidence_scores": True,
        },
    }
    assert set(SCHEMA["properties"]) == {"title", "authors", "abstract", "keywords", "publication_year"}
    assert reading.values["title"] == "Two column study"
    assert reading.field_metadata["title"]["confidence"] == 0.97
    assert reading.credits == Decimal("15.0")


def test_a_failed_job_is_an_extraction_error_that_never_carries_the_vendors_message():
    vendor = Vendor(statuses=("FAILED",), error_message="secret/path/manuscript.pdf exploded")

    with pytest.raises(ExtractionError) as raised:
        reader(vendor).read(PARSE_JOB_ID)

    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("answer", [httpx.Response(503), httpx.Response(429), httpx.ConnectError("down")])
def test_an_unreachable_or_refusing_vendor_is_unavailable(answer):
    vendor = Vendor(failure=("create", answer))

    with pytest.raises(ExtractorUnavailable):
        reader(vendor).read(PARSE_JOB_ID)


def test_a_job_still_running_past_its_budget_is_unavailable():
    ticks = iter(range(0, 10_000, 100))
    vendor = Vendor(statuses=("RUNNING",))

    with pytest.raises(ExtractorUnavailable):
        reader(vendor, timeout_seconds=250, clock=lambda: next(ticks)).read(PARSE_JOB_ID)


def test_only_extract_credits_are_reported_since_the_parse_was_charged_already():
    reading = Vendor().reading
    reading["usage"] = {"credits": 45.0, "extract_credits": 15.0, "parse_credits": 30.0}

    assert reader(Vendor(reading=reading)).read(PARSE_JOB_ID).credits == Decimal("15.0")
