"""Low-confidence pages are flagged, never dropped; watermarks shown (IR-841)."""

from apps.ai.extraction import page_report

RAW = {"metadata": {"pages": [
    {"page_number": 1, "confidence": 0.95, "printed_page_number": "i"},
    {"page_number": 2, "confidence": 0.3, "printed_page_number": "ii", "watermark": "DRAFT|CONFIDENTIAL"},
    {"page_number": 3, "confidence": None, "printed_page_number": None},
]}}


def test_low_confidence_pages_are_flagged_and_none_are_dropped():
    report = page_report(RAW)

    assert [line.split(":")[0] for line in report.splitlines()] == ["p2 (ii)", "p1 (i)", "p3"]
    assert "LOW" in report.splitlines()[0]
    assert "LOW" not in report.splitlines()[1]
    assert "unscored" in report.splitlines()[2]


def test_watermarks_are_shown_on_their_page():
    assert "watermark DRAFT|CONFIDENTIAL" in page_report(RAW).splitlines()[0]


def test_an_extraction_without_a_raw_result_reports_nothing():
    assert page_report({}) == ""
